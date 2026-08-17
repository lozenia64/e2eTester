# CI 파이프라인 전면 리뉴얼 — Design

**작성일:** 2026-08-17
**상태:** 승인됨 (구현 계획 대기)
**대상:** `.github/workflows/ci.yml`, `scripts/ci/`, `pyproject.toml`, `requirements-dev.txt`, `docs/INSTALL.md`, `docs/CI.md`

---

## 1. 문제

### 1.1 SSOT 가 SSOT 가 아니다 (근본 원인)

`scripts/ci/gates.py` 는 스스로를 다음과 같이 선언한다.

```python
"""CI gate SSOT — GitHub Actions and scripts/ci/run_all_gates.py."""
```

그러나 `.github/workflows/ci.yml` 은 `gates.py` 를 **한 번도 참조하지 않는다.** 게이트 명령어를 워크플로 YAML 에 인라인으로 다시 적어 놓았고, 두 곳이 독립적으로 표류했다. 그 결과 **게이트 4개가 GitHub Actions 에서 단 한 번도 실행된 적이 없다.**

| 게이트 | `docs/CI.md` Tier 표 | PR 템플릿 체크박스 | 로컬 러너 | **GitHub Actions** |
| --- | --- | --- | --- | --- |
| `import_contracts` | 약속함 (Tier 1) | 약속함 | 실행 | **미실행** |
| `pyright_decider` | — | 약속함 | 실행 | **미실행** |
| `projection_validate` | 약속함 (Tier 1) | 약속함 | 실행 | **미실행** |
| `snapshot_validate` | 약속함 (Tier 1) | 약속함 | 실행 | **미실행** |

측정 결과 4개 모두 **현재 통과하며 합계 약 10초**다 (`import_contracts` 709ms, `pyright_decider` 6,774ms, `projection_validate` 1,294ms, `snapshot_validate` 891ms). 비용이 사실상 없는데도 빠져 있었다는 뜻이고, 다음 두 계약이 PR 에서 강제되지 않고 있었다.

- **아키텍처 경계 계약** (import-linter): 도메인 순수성, Playwright 격리, 컨텍스트 격리, 실행 평면 분리
- **decider 망라성** (pyright `reportMatchNotExhaustive`): `evolve` 분기 누락 탐지

### 1.2 security paths-filter 유령 경로

`ci.yml` 의 `changes` job 이 참조하는 두 경로가 실재하지 않는다.

| `ci.yml` 이 참조하는 경로 | 실제 위치 |
| --- | --- |
| `app/storage/input_crypto.py` | `app/platform/security/input_crypto.py` |
| `app/storage/*input*` | `app/contexts/run/infrastructure/encrypted_run_input_store.py`<br>`app/contexts/suite/infrastructure/encrypted_suite_input_store.py` |

`app/storage/` 디렉터리 자체가 존재하지 않는다. **at-rest 암호화 코드를 수정해도 `ci / security` 가 발화하지 않는다.**

### 1.3 bandit 이 정작 암호화 구현체를 스캔하지 않는다

스캔 대상은 `app/contexts/identity`, `routes_trigger.py`, `routes_otp.py` 뿐이다. AES-GCM 구현체인 `app/platform/security/input_crypto.py` 가 빠져 있다.

### 1.4 pip 캐시 키 오류

```yaml
cache-dependency-path: requirements-dev.txt
```

`requirements-dev.txt` 는 첫 줄이 `-r requirements.txt` 다. 런타임 의존성만 변경되면 **캐시 키가 그대로라 낡은 휠을 재사용한다.**

### 1.5 merge queue 취소 위험

`cancel-in-progress: true` 가 `merge_group` 이벤트에도 적용된다. 큐 검증이 중도 취소될 수 있다.

### 1.6 Python 버전 패리티 없음

CI 는 3.11 단독, 개발자 로컬은 3.13. `docs/INSTALL.md` 는 `Python 3.11+` 로 공표. 어느 쪽도 상대를 검증하지 않는다.

---

## 2. 목표 / 비목표

### 목표

1. **드리프트를 구조적으로 불가능하게 만든다.** 게이트를 `gates.py` 에 추가하면 CI job 이 자동 생성된다.
2. **유령 경로를 고치고, 재발을 CI 가 스스로 잡게 한다.**
3. 브랜치 보호 규칙을 **다시는 손대지 않아도 되게** 한다.
4. Python 3.13 단일 기준으로 정리한다.
5. 커버리지 하락을 래칫으로 차단한다.

### 비목표 (명시적으로 하지 않음)

- Python 3.11 + 3.13 매트릭스 — 3.13 단일 상향으로 대체
- `pip-audit` 상시 실행 — 기존 조건부 유지
- PR 요약 코멘트 / Step Summary 렌더링
- 라이브 Playwright E2E 의 CI 편입 (기존 방침대로 CI 밖 유지)

---

## 3. 아키텍처

### 3.1 3-job 구조

```
┌──────────┐     gates JSON      ┌──────────────────┐    ┌───────────────┐
│   plan   │ ──────────────────▶ │ gate (matrix)    │ ─▶ │ ci / required │
│          │  ["ruff","pytest",  │  ci / ruff       │    │   (집계)       │
│ gates.py │   "import_contracts"│  ci / pytest     │    │               │
│  가 결정  │        ...]         │  ci / ...        │    │ 브랜치 보호는  │
└──────────┘                     └──────────────────┘    │ 이것 하나만    │
                                  fail-fast: false        └───────────────┘
```

**`plan`** — 변경 파일을 판정해 실행할 게이트 목록을 JSON 으로 출력한다.
**`gate`** — matrix 로 게이트당 job 하나. `fail-fast: false` 라 하나가 깨져도 나머지 결과를 전부 볼 수 있다.
**`required`** — 집계 job. **브랜치 보호가 가리키는 유일한 체크.**

### 3.2 왜 이 구조인가

- 게이트별 job 이라 GitHub UI 에서 어느 게이트가 깨졌는지 즉시 보인다 (단일 job 방식의 단점 해소).
- matrix 원본이 `gates.py` 라 **워크플로에 게이트 목록이 중복 기재되지 않는다.** §1.1 의 재발 경로가 사라진다.
- required check 이름이 `ci / required` 하나로 고정되므로, 게이트가 늘고 줄어도 브랜치 보호 규칙은 불변이다.

### 3.3 경로 글롭을 `gates.py` 로 이관

현재 경로 글롭은 `ci.yml` 의 `dorny/paths-filter` 안에 있다. 이를 `gates.py` 상수로 옮기고 `dorny/paths-filter` 의존을 제거한다.

```python
# scripts/ci/gates.py
SECURITY_PATHS: list[str] = [
    "app/contexts/identity/**",
    "app/platform/security/**",
    "app/contexts/*/infrastructure/encrypted_*_input_store.py",
    "app/api/routes_trigger.py",
    "app/api/routes_otp.py",
    "requirements.txt",
    "requirements-dev.txt",
]
DOCS_ONLY_PATHS: list[str] = ["docs/**", "**/*.md"]
```

**이유:** 경로 글롭이 `ci.yml` 에 남아 있으면 §1.2 유령 경로가 정확히 같은 방식으로 재발한다. `gates.py` 로 옮기면 Python 코드라 단위 테스트로 검증할 수 있고, `ci_config_valid` 게이트가 실재성을 강제할 수 있다.

---

## 4. 컴포넌트 설계

### 4.1 `scripts/ci/plan.py` (신규)

**책임:** 변경 파일 → 실행할 게이트 목록.

```
입력:  --base-ref <git ref>   (PR 의 base, push 의 before)
       --github-output <path> (선택, 없으면 stdout)
출력:  gates=["docs_consistency","ruff",...]   ← $GITHUB_OUTPUT 형식
       scope=code|docs_only|security
```

**판정 규칙**

| 변경 내용 | 프로필 | 결과 게이트 |
| --- | --- | --- |
| `docs/**`, `*.md` 만 | `docs_only` | `docs_consistency`, `architecture_gates`, `ci_config_valid` |
| 그 외 코드 변경 | `full` | `CI_STANDARD_GATES` + `ci_config_valid` |
| `SECURITY_PATHS` 매칭 포함 | 위 + 보안 | `+ pip_audit`, `+ bandit_security` |
| `schedule` 이벤트 | 주간 감사 | 위 전체 (보안 포함) |

여기서 `CI_STANDARD_GATES` 는 기존 `STANDARD_GATES` 에서 **`pytest` 를 빼고 `coverage` 를 넣은** 목록이다 (§4.4 — `coverage` 가 `pytest` 를 흡수하므로 둘을 함께 넣으면 테스트가 두 번 돈다). 기존 `STANDARD_GATES` 는 로컬 러너용으로 그대로 둔다.

**빈 목록 금지.** 어떤 경우에도 최소 1개(`ci_config_valid`)를 반환한다. GitHub Actions 는 빈 matrix 를 오류로 처리하기 때문이다.

**base-ref 해석:** `plan` job 만 `fetch-depth: 0` 으로 체크아웃하고 `git diff --name-only <base>...HEAD` 를 쓴다. `gate` job 들은 얕은 체크아웃으로 충분하다.

### 4.2 `scripts/ci/run_all_gates.py` — `--gate` 추가

matrix leg 하나가 게이트 하나만 실행하도록 단일 게이트 모드를 추가한다. 기존 `--profile` 동작은 그대로 둔다 (로컬 pre-PR 용도).

```
python3 scripts/ci/run_all_gates.py --gate ruff
```

### 4.3 `ci_config_valid` 게이트 (신규)

**이 설계에서 가장 중요한 신규 장치.** §1.2 를 영구히 차단한다.

검사 항목:

1. `gates.py` 의 `SECURITY_PATHS` 의 **모든 글롭이 최소 1개 실파일에 매칭**되는지
2. `GATE_COMMANDS` 안의 모든 파일 경로 인자(`scripts/*.py`, `app/**`)가 실재하는지
3. `GATE_TIERS` 가 모든 게이트를 커버하는지 (누락 시 tier 99 로 조용히 밀리는 것 방지)
4. `PROFILE_GATES` 의 모든 게이트 이름이 `GATE_COMMANDS` 또는 `PREFLIGHT_GATES` 에 실재하는지

오늘 발견된 `app/storage/input_crypto.py` 는 검사 1·2 에서 즉시 실패했을 것이다.

### 4.4 `coverage` 게이트 (신규)

- `pytest-cov` 를 `requirements-dev.txt` 에 추가
- 바닥선은 `pyproject.toml` 의 `[tool.coverage.report] fail_under` 가 소유 (SSOT)
- **초기값 57** — 측정 실측치 58% (18,416 구문 중 7,648 미커버, 621 passed) 바로 아래

**왜 58 이 아니라 57 인가:** 정확히 실측치로 잡으면 무해한 리팩터링에도 CI 가 빨개진다. 게이트가 미움받으면 우회당한다. 1%p 완충은 실질적 하락만 잡는다.

**래칫 운용:** 커버리지가 올라가면 `fail_under` 숫자 한 줄을 올리는 PR 을 낸다. 자동 상향은 하지 않는다 — 조용한 자동 변경은 리뷰를 못 받는다.

`coverage` 게이트는 `pytest --cov` 를 한 번 실행해 **테스트 실행과 커버리지 측정을 겸한다.** 따라서 CI 게이트 목록에서 `pytest` 를 빼고 `coverage` 를 넣는다(§4.1의 `CI_STANDARD_GATES`). 둘을 함께 넣으면 621개 테스트가 두 번 돌아 CI 시간이 2배가 된다.

로컬 러너의 `STANDARD_GATES` 는 `pytest` 를 유지한다. 로컬에서는 커버리지 측정 없이 빠르게 돌리고 싶은 경우가 많고(측정 시 136초 vs 116초), 래칫 확인이 필요하면 `--profile full` 대신 `--gate coverage` 를 쓰면 된다.

---

## 5. 게이트 인벤토리 (변경 전후)

| 게이트 | 현재 CI | 변경 후 | 비고 |
| --- | --- | --- | --- |
| `docs_consistency` | 실행 | 실행 | |
| `architecture_gates` | 실행 | 실행 | |
| `ruff` | 실행 | 실행 | target `py313` 으로 상향 |
| `ruff_format` | 실행 | 실행 | |
| `pytest` | 실행 | `coverage` 로 흡수 | `--cov` 동반 실행 |
| `import_contracts` | **미실행** | **실행** | §1.1 복구 |
| `pyright_decider` | **미실행** | **실행** | §1.1 복구 |
| `projection_validate` | **미실행** | **실행** | §1.1 복구 |
| `snapshot_validate` | **미실행** | **실행** | §1.1 복구 |
| `pip_audit` | 조건부 | 조건부 (경로 수정됨) | |
| `bandit_security` | 조건부 | 조건부 + 범위 확대 | `app/platform/security` 추가 |
| `ci_config_valid` | — | **신규 · 항상 실행** | §4.3 |
| `coverage` | — | **신규** | §4.4 |

---

## 6. 설정 변경

### 6.1 Python 3.13 단일 상향

| 위치 | 현재 | 변경 후 |
| --- | --- | --- |
| `ci.yml` (4곳) | `3.11` | `3.13` |
| `pyproject.toml` `[tool.ruff] target-version` | `py311` | `py313` |
| `pyproject.toml` `[tool.pyright] pythonVersion` | `3.11` | `3.13` |
| `docs/INSTALL.md:7` | `Python 3.11+` | `Python 3.13+` |

**근거:** 3.11 은 아무것도 강제하지 않는 선택값이었다. 로컬 3.13.14 에서 621 테스트 전부 통과하며, `pyright --pythonversion 3.13` 도 0 errors 다.

**주의:** `INSTALL.md` 를 함께 고치지 않으면 "3.11+ 지원" 이라는 미검증 선언이 남는다. 선언과 검증 범위는 반드시 일치시킨다.

### 6.2 PEP 695 마이그레이션 (런타임 코드)

`ruff --target-version py313` 실행 시 신규 에러 3건:

| 파일 | 규칙 | 대상 |
| --- | --- | --- |
| `app/ai/gemini_client.py:61` | UP047 | `_parse_structured_response` |
| `app/ai/gemini_client.py:73` | UP047 | `generate_structured_with_fallback` |
| `app/realtime/listener_registry.py:10` | UP046 | `class ListenerRegistry(Generic[E])` |

`TypeVar`/`Generic[...]` → PEP 695 문법(`def f[T](...)`, `class C[E]:`)으로 전환한다. 기계적 변환이며 런타임 의미 변화가 없다. **이번 작업에서 앱 코드를 건드리는 유일한 항목이므로 621 테스트로 검증한다.**

### 6.3 버그 수정

```yaml
# 캐시 키 — requirements.txt 변경도 캐시를 무효화하도록
cache-dependency-path: |
  requirements.txt
  requirements-dev.txt

# merge queue 검증은 취소하지 않는다
cancel-in-progress: ${{ github.event_name != 'merge_group' }}
```

---

## 7. 오류 처리

| 상황 | 동작 |
| --- | --- |
| `plan` 이 실패 | `gate` 미실행 → `required` 가 `failure` 감지 → PR 차단 |
| 게이트 하나 실패 | `fail-fast: false` 라 나머지 계속 → `required` 실패 |
| matrix 가 비어 있음 | `plan` 이 최소 1개 보장 (§4.1) — 발생 불가 |
| `gate` job 이 skipped | `required` 는 `failure`/`cancelled` 만 실패로 본다 → 통과 |
| 게이트가 cancelled | `required` 실패 (부분 검증으로 머지되는 것을 막음) |

`required` 판정 로직:

```yaml
required:
  name: ci / required
  needs: [plan, gate]
  if: always()
  steps:
    - run: |
        if [ "${{ contains(needs.*.result, 'failure') }}" = "true" ] || \
           [ "${{ contains(needs.*.result, 'cancelled') }}" = "true" ]; then
          echo "::error::하나 이상의 게이트가 실패했습니다"
          exit 1
        fi
```

---

## 8. 테스트 전략

워크플로 YAML 자체는 로컬에서 실행 검증이 불가능하다. 따라서 **판단 로직을 전부 Python 으로 밀어 넣고 단위 테스트로 덮는다.** 이것이 §3.3 에서 경로 글롭을 `gates.py` 로 옮기는 또 하나의 이유다.

| 대상 | 테스트 | 검증 내용 |
| --- | --- | --- |
| `plan.py` | `tests/test_ci_plan.py` (신규) | docs-only → 3개 게이트 / 코드 변경 → full / 보안 경로 → 보안 게이트 추가 / 빈 목록 반환 안 함 / `$GITHUB_OUTPUT` JSON 형식 |
| `ci_config_valid` | `tests/test_ci_config_valid.py` (신규) | 실재 경로 통과 / **유령 경로 주입 시 실패** (오늘의 버그를 회귀 테스트로 고정) |
| `run_all_gates.py --gate` | `tests/test_ci_plan.py` | 단일 게이트 실행, 미지 게이트명은 오류 |
| PEP 695 변환 | 기존 621 테스트 | 런타임 동작 불변 |
| 전체 | `run_all_gates.py --profile full` | 최종 통합 확인 |

**회귀 테스트를 반드시 넣는다:** `SECURITY_PATHS` 에 존재하지 않는 경로를 넣으면 `ci_config_valid` 가 실패해야 한다. 이 테스트가 §1.2 재발을 영구히 막는 장치다.

---

## 9. 마이그레이션 / 롤아웃

### 사람이 해야 하는 작업 (자동화 불가)

이 변경은 required check 이름을 바꾼다.

| 현재 required check | 변경 후 |
| --- | --- |
| `ci / docs`, `ci / lint`, `ci / test` | **`ci / required` 하나** |

**머지 전에 GitHub 브랜치 보호 규칙을 수동으로 갱신해야 한다.** 갱신하지 않으면 존재하지 않는 체크 이름을 기다리며 PR 이 영구히 머지되지 않는다.

권장 순서:

1. 이 PR 을 올려 새 체크가 실제로 도는 것을 확인
2. 브랜치 보호에 `ci / required` 를 **추가** (기존 것은 아직 유지)
3. 새 체크가 통과하는 것을 확인한 뒤 기존 3개를 **제거**
4. 머지

이후로는 게이트가 늘거나 줄어도 브랜치 보호는 불변이다.

### `ci / security` 관련 기존 주의사항 유지

`docs/CI.md` 의 "`ci / security` 를 required 로 거는 것은 비권장 — 조건부 skip 시 merge queue 가 멈춘다"는 경고는 새 구조에서 근거를 잃는다.

이유는 "숨어서" 가 아니라 **애초에 체크가 생기지 않기 때문**이다. 기존 구조에서는 `ci / security` job 이 `if:` 조건으로 skip 되어도 체크 이름 자체는 존재해 브랜치 보호가 이를 기다렸다. 새 구조에서는 `plan` 이 보안 게이트를 matrix 에 **넣지 않으므로** 해당 체크가 생성되지 않고, 브랜치 보호가 보는 이름은 언제나 `ci / required` 하나뿐이다. 따라서 조건부 게이트의 존재 자체를 브랜치 보호가 알 필요가 없다.

이 경고 문구는 §11 에 따라 `docs/CI.md` 에서 갱신한다.

---

## 10. 리스크

| 리스크 | 심각도 | 완화 |
| --- | --- | --- |
| 브랜치 보호 미갱신으로 PR 머지 불가 | **높음** | §9 단계적 전환. 이 문서와 PR 본문에 명시 |
| PEP 695 변환이 런타임 동작을 바꿈 | 중 | 621 테스트로 검증. 기계적 변환이라 가능성 낮음 |
| `plan.py` 의 base-ref 해석이 이벤트별로 다름 | 중 | PR/push/merge_group/schedule 각각 단위 테스트 |
| 커버리지 게이트가 초반에 자주 빨개짐 | 낮음 | 1%p 완충. 문제 시 `fail_under` 하향은 한 줄 |
| 3.13 상향으로 의존성 호환 문제 | 낮음 | 로컬 3.13.14 에서 621 테스트 통과 확인됨 |
| `dorny/paths-filter` 제거로 판정 로직 회귀 | 중 | 판정을 Python 으로 옮겨 단위 테스트로 덮음 (§8) |

---

## 11. 문서 갱신 대상

| 문서 | 변경 |
| --- | --- |
| `docs/CI.md` | 게이트 계층 표에 `ci_config_valid`·`coverage` 추가, GitHub Actions 표를 `ci / required` 단일 체크로 교체, 실행 예시 갱신 |
| `docs/INSTALL.md` | `Python 3.11+` → `Python 3.13+` |
| `.github/pull_request_template.md` | 체크리스트 문구를 새 러너 사용법에 맞춰 확인 |

`docs/CI.md` 의 Tier 표가 §1.1 에서 "약속했지만 실행 안 되던" 상태였으므로, 이번에 표와 실제가 일치하게 된다.
