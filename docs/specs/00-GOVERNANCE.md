# SDD 거버넌스

E2E Tester 프로젝트의 Spec-Driven Development 운영 규칙.

## 1. Spec의 정의

**Spec**은 다음을 명시하는 문서다:

- **누가** (액터)
- **무엇을** (기능 요구사항 FR)
- **어떤 조건에서** (전제·입력)
- **어떻게 검증하는지** (수용 기준 AC)
- **무엇이 범위 밖인지** (Out of scope)

Spec은 구현 세부(클래스명·알고리즘)보다 **관측 가능한 행동**에 집중한다.

## 2. SSOT 및 Spec 동기화 규칙

프로젝트 전체의 문서 위치·SSOT 매트릭스·PR 체크리스트 정본은 [`docs/DOCS_GOVERNANCE.md`](../DOCS_GOVERNANCE.md)다. SDD 관점에서 변경 유형별 Spec 갱신 대상은 다음과 같다:

| 변경 유형 | Spec 및 짝 문서 갱신 대상 |
| --- | --- |
| 새 기능·행동·상태 전이 변경 | 해당 도메인 `docs/specs/**` (신규 SPEC ID 시 [`docs/specs/README.md`](README.md) 인덱스 동시 등록) |
| 새 API 엔드포인트 | 해당 도메인 Spec + [`docs/E2E_ARCHITECTURE.md`](../E2E_ARCHITECTURE.md) §5.2 |
| manifest 모듈·시스템 추가/변경 | `SPEC-SYS-*` (`docs/specs/systems/{code}.md`) + `docs/scenarios/{code}.md` |
| env 변수 추가/변경 | 해당 Spec + [`docs/INSTALL.md`](../INSTALL.md) + `.env.example` |
| 아키텍처·프론트엔드 경계 변경 | `SPEC-PLATFORM-*` + [`docs/E2E_ARCHITECTURE.md`](../E2E_ARCHITECTURE.md) / [`docs/CI.md`](../CI.md) |
| 사용자 대면 문구·상태 라벨 | 해당 Spec AC + 구현(한국어, 상태 라벨은 `app/core/status_labels.py` → `gen_frontend_tokens.py`) |

## 3. Spec 수명주기

```text
draft → approved → (구현) → (검증) → deprecated
```

| 상태 | 의미 |
| --- | --- |
| `draft` | 작성 중, Agent 구현 금지 |
| `approved` | 구현·수정 허용 |
| `deprecated` | 대체 Spec 참조, 신규 구현 금지 |

**현황:** 초기 코드베이스 역공학(2026-08) 및 이후 SDD로 작성·통합된 현행 Spec 모두 `approved` 상태로 관리한다.

## 4. AI Agent 작업 프로토콜

### 4.1 작업 시작

1. 사용자 요청에서 **SPEC ID** 매핑 ([`docs/specs/README.md`](README.md) 인덱스)
2. 해당 Spec + **의존 Spec** + SSOT 링크 읽기
3. Spec에 없는 요구사항 → 사용자에게 Spec 추가·갱신 여부 확인

### 4.2 구현 중

- Spec의 FR/AC를 체크리스트로 사용
- 도메인 규칙 변경 시 `RunStateMachine`·`RunAggregate`·`SuiteStateMachine`·`SuiteAggregate`·`decider.py`(`decide`/`evolve`) 등 **순수 계층** 우선
- 백엔드 아키텍처 게이트(`AG-001~009`, `import_contracts`, `pyright_decider`) 및 프론트엔드 게이트(`FG-001~007`, `frontend_tokens`) 위반 금지 (`SPEC-PLATFORM-005`, [`docs/CI.md`](../CI.md))

### 4.3 완료

1. AC별 검증 (`@pytest.mark.spec` 단위·통합 테스트, Vitest, 또는 UI 변경 시 [`.agents/skills/e2e-browser/SKILL.md`](../../.agents/skills/e2e-browser/SKILL.md) 수동 브라우저 검증)
2. `python3 scripts/ci/run_all_gates.py --profile full` 및 커버리지 확인(`--gate coverage`)
3. Spec 및 짝 문서 변경을 동일 PR에 포함 ([`docs/DOCS_GOVERNANCE.md`](../DOCS_GOVERNANCE.md) PR 체크리스트 준수)

## 5. Spec 구조 및 분해 원칙

- 신규 Spec은 [`docs/specs/_TEMPLATE.md`](_TEMPLATE.md) 구조를 기반으로 작성한다.
- **한 Spec = 한 책임 영역** (예: OTP는 `SPEC-RUN-002`, Suite OTP는 `SPEC-SUITE-001`에 교차 참조).
- 시스템 E2E는 **시스템당 1 Spec** (`SPEC-SYS-*`, `docs/specs/systems/{code}.md`)을 원칙으로 하되, 다채널 공통 규칙은 `_` 접두사 파일(예: `_shared-rep-homepage.md`)로 분리해 참조할 수 있다.
- 단일 Spec이 지나치게 비대해지면(약 350줄 초과) 응집도를 해치지 않는 선에서 하위 Spec 분할을 검토한다.

## 6. 기계 검증 vs 수동 검증

전체 CI 게이트 계층(Tier 0~3)은 [`docs/CI.md`](../CI.md) 및 [`SPEC-PLATFORM-005`](platform/05-ci-gates.md)를 참조한다. SDD 명세와 직결되는 검증 분담은 다음과 같다:

| 검증 대상 | 도구 | 비고 |
| --- | --- | --- |
| manifest ↔ 시나리오 ↔ 시스템 Spec `module_id` | `scripts/check_docs_consistency.py` | CI tier 0 (`_` 접두사 공유 Spec 제외 1:1) |
| Spec 인덱스(`docs/specs/README.md`) 링크 파일 실재 | `scripts/check_docs_consistency.py` | CI tier 0 |
| API·env·Gemini 모델 체인·§4 폴더 트리 양방향 | `scripts/check_docs_consistency.py` | CI tier 0 |
| 프론트엔드 규칙(FG-001~007)·상태 토큰·Vitest | `check_frontend_gates.py`, `gen_frontend_tokens.py`, `npm run test` | CI tier 0 |
| 아키텍처 경계(AG-001~009)·import 계약·Decider 타입·이벤트/스냅샷 결정성 | `check_architecture_gates.py`, `importlinter`, `pyright`, `rebuild_*.py` | CI tier 1 |
| `@pytest.mark.spec` ↔ Spec 파일·AC 섹션 실재 | `tests/test_spec_traceability.py` | CI tier 2 (`pytest` / `coverage`) |
| Spec Gherkin 시나리오 의미·실브라우저 E2E | `@pytest.mark.spec` 테스트·PR 리뷰·수동 Run | 라이브 사이트 E2E는 CI 밖 |

**주의:** `approved` 상태가 곧 모든 AC의 자동화 테스트 완비를 뜻하지는 않는다. AC와 테스트 연결이 빈약한 Spec은 구현·수정 작업 시 함께 보강한다.

### 6.1 `@pytest.mark.spec` (SDD 추적성 규칙)

수용 기준과 pytest 테스트를 마커로 연결한다:

```python
@pytest.mark.spec("SPEC-RUN-001", "AC-002")
def test_post_step_rejects_input_not_declared_in_manifest(): ...
```

`tests/test_spec_traceability.py` 통과를 위한 Spec 문서 작성 규칙:
1. Spec 파일 본문(상단 메타데이터 표 등)에 백틱으로 감싼 `` `SPEC-XXX-NNN` `` ID가 명시되어야 한다.
2. 수용 기준 섹션 헤더는 반드시 콜론(`:`)을 포함한 **`### AC-NNN: 제목`** 형식이어야 한다 (`^### (AC-\d+):`).
3. 파일명이 `_`로 시작하는 문서(`_TEMPLATE.md`, `_shared-rep-homepage.md`)는 마커 타겟 스캔에서 제외된다.
4. 신규 AC 테스트 추가 시 해당 Spec의 테스트 요구사항 표도 함께 갱신하며, `pytest -m spec` 으로 마커 테스트만 필터링해 실행할 수 있다.
