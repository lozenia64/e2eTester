# CI 검증 프로세스

e2eTester의 GitHub Actions CI는 **순수 레이어 단위 테스트 + 문서/아키텍처 정책 + 정적 품질**에 집중한다. Playwright 라이브 사이트 E2E는 PR 게이트에 포함하지 않는다(OTP·외부 의존·플레이크).

## SSOT (단일 진실원천)

| 구성요소 | 경로 |
| --- | --- |
| 게이트 정의 | [`scripts/ci/gates.py`](../scripts/ci/gates.py) |
| 로컬 전체 실행 | `python3 scripts/ci/run_all_gates.py` |
| 오케스트레이터 QC | `.cursor/skills/e2e-orchestrator/scripts/run_gates.py` |
| GitHub Actions | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) |

로컬에서 PR 전에 실행:

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/ci/run_all_gates.py --profile full
```

조건부 보안 게이트(auth/PII/OTP 터치):

```bash
python3 scripts/ci/run_all_gates.py --profile platform --risk-flags pii,auth
```

## 게이트 계층 (Tier)

| Tier | 게이트 | 설명 |
| --- | --- | --- |
| 0 | `ruff`, `ruff_format`, `docs_consistency` | 즉시 실패 (~10–30초) |
| 1 | `architecture_gates` | 정책-as-code (AG-001~008) |
| 1 | `import_contracts` | import 그래프 경계 계약 (`lint-imports` — pyproject `[tool.importlinter]`: 도메인 순수성·코어 무-Playwright) |
| 1 | `projection_validate` | 이벤트 재생 ↔ 라이브 projection 지문 일치 (`scripts/rebuild_projections.py --validate`) |
| 1 | `snapshot_validate` | 이벤트 폴드 ↔ 라이브 aggregate_snapshots 동등 (`scripts/rebuild_snapshots.py --validate`) |
| 2 | `pytest` | 순수 도메인/오케스트레이터 단위 테스트 |
| 3 | `pip_audit`, `bandit_security` | auth/PII 경로 변경 또는 주간 schedule |

### 아키텍처 게이트 (`scripts/check_architecture_gates.py`)

| 규칙 | 내용 |
| --- | --- |
| AG-001 | `app/` 내 `list_runs()` 직접 호출 금지 |
| AG-002 | `app/orchestrator/` 에서 `playwright` import 금지 |
| AG-003 | `app/domain/` 에 I/O·async 런타임 import 금지 |
| AG-004 | `app/orchestrator/` 에서 `list_all_runs()` / `list_runs_since()` 금지 |
| AG-005 | `app/` 에서 aggregate `.snapshot` / `.suite` 직접 접근 금지 (`domain`/`storage`/`tests` 제외) |
| AG-006 | 스텝 계층(`app/automation`·`app/systems`·`app/runner`)에서 `print(` / `redirect_stdout` 금지 (전역 stdout 경합 방지 — `step_logging.log`·`ctx.log` 만; 매뉴얼 CLI `login_phone.py` 제외) |
| AG-007 | 질의 포트(`app/storage/ports.py` `*QueryPort`)의 반환 타입에 `Run`/`SuiteRun` 엔티티 금지 (읽기 경로는 화면형 DTO 만) |
| AG-008 | 오케스트레이터 서비스(`run_service.py`·`suite_service.py`)에서 `run`/`suite`/`step`/`module` 필드 직접 대입 금지 (애그리거트가 유일한 상태 변이자) |

프로젝션/스냅샷 정합성 검증(선택·Tier 1):

```bash
python3 scripts/rebuild_projections.py --validate --db data/e2etester.db
python3 scripts/rebuild_snapshots.py --validate --db data/e2etester.db
```

`projection_validate` 는 이벤트 재생이 라이브 projection 지문과 일치하는지, `snapshot_validate` 는 이벤트 폴드(`app/domain/run_decider.py:rebuild_state`)가 라이브 `aggregate_snapshots` 와 도메인 동등한지 검증한다 — 둘 다 "이벤트=진실"의 실증 관문이다. CI 표준 게이트(`run_all_gates.py --profile full`)는 빈 DB 파일(`data/.ci_projection_validate.db`·`data/.ci_snapshot_validate.db`)로 동일 검증을 수행한다.

## GitHub Actions job 구조

워크플로: **`ci`** (`.github/workflows/ci.yml`)

| Required check 이름 | Job | 조건 |
| --- | --- | --- |
| `ci / lint` | ruff check + format | 코드 변경 시 |
| `ci / docs` | docs consistency + architecture | 항상 |
| `ci / test` | pytest | 코드 변경 시 |
| `ci / security` | pip-audit + bandit | auth/PII 경로 또는 월요일 03:00 UTC schedule |

`ci / changes`는 path filter 전용이며 required check로 등록하지 않는다.

### Path filter

- **docs-only PR** (`docs/**`, `*.md` 만 변경): `ci / docs` 만 실행 (lint·test 스킵)
- **security 경로** (`app/auth/**`, OTP/trigger 라우트, input store, requirements): `ci / security` 추가

### merge queue

merge queue 사용 시 워크플로에 `merge_group` 트리거가 이미 포함되어 있다. branch protection / ruleset에서 **required check 이름이 job `name:` 과 정확히 일치**해야 한다:

- `ci / lint`
- `ci / docs`
- `ci / test`

`ci / security`는 조건부이므로 required check에 넣을 경우, security 경로가 없는 PR에서는 job이 skip되어 merge queue가 멈출 수 있다. **권장: security는 required가 아닌 정보성 게이트**로 두고, auth/PII 변경 PR에서는 수동으로 security job 통과를 확인한다.

## Branch protection / ruleset 설정 (운영)

GitHub 저장소 **Settings → Rules → Rulesets** (또는 Branch protection rules):

1. **Target branch:** `main`
2. **Require status checks:**
   - `ci / docs` (필수)
   - `ci / lint` (필수 — docs-only PR은 job skip되므로 ruleset에서 “Do not require” 옵션이 있으면 활용, 없으면 docs-only PR도 lint 통과 필요)
3. **Require pull request reviews:** 팀 정책에 따름
4. **Require merge queue** (선택): 팀 동시 merge가 많을 때 활성화. 활성화 후 첫 PR에서 `gh-readonly-queue/...` 브랜치에 checks가 뜨는지 확인

### docs-only PR과 required checks

`ci / lint`·`ci / test`가 skip되면 GitHub는 해당 check를 “통과(skipped)”로 처리한다. merge queue 사용 시 skipped job이 required check로 설정되어 있어도 일반적으로 merge 가능하다. 문제가 있으면 ruleset에서 check 목록을 재검토한다.

## e2e-orchestrator 연동

| 프로필 | 게이트 |
| --- | --- |
| `step_fix`, `new_module`, `platform`, `healing_patch` | Tier 0–2 표준 |
| `new_system` | Tier 0–2 + Tier 3 security |
| `docs_only` | docs + architecture |
| `risk_flags`: `pii`, `otp`, `auth` | 표준 + Tier 3 security |

QC-T (`e2e-test-runner`)는 `run_gates.py` → `gates-report.json`을 생성한다.

## PR Definition of Done

[docs/DOCS_GOVERNANCE.md](DOCS_GOVERNANCE.md) 및 [`.github/pull_request_template.md`](../.github/pull_request_template.md) 체크리스트를 따른다.

## 의도적으로 CI 밖

- Playwright 라이브 사이트 Run/Suite (OTP, 실제 보험 URL)
- AI failure analysis / SMTP (선택 기능, env 미설정 시 no-op)

수동 검증: 서버 기동 후 대시보드에서 Run 실행.
