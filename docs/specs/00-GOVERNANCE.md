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

## 2. SSOT 계층

```text
[행동·AC·UX]  docs/specs/          ← AI Agent 1차 입력
[아키텍처·API] docs/E2E_ARCHITECTURE.md
[시나리오·모듈] docs/scenarios/{code}.md
[설치·env]     docs/INSTALL.md, .env.example
[런타임 기본값] 소스코드 + check_docs_consistency.py
```

### 동기화 규칙

| 변경 유형 | 갱신 대상 |
| --- | --- |
| 새 API 엔드포인트 | Spec (해당 도메인) + `E2E_ARCHITECTURE.md` §5.2 |
| manifest 모듈 추가/변경 | `SPEC-SYS-*` + `docs/scenarios/{code}.md` |
| env 변수 추가 | Spec (해당) + `INSTALL.md` + `.env.example` |
| 아키텍처 경계 변경 | `SPEC-PLATFORM-*` + `E2E_ARCHITECTURE.md` |
| 사용자 대면 문구 | Spec AC + 구현(한국어) |

## 3. Spec 수명주기

```text
draft → approved → (구현) → (검증) → deprecated
```

| 상태 | 의미 |
| --- | --- |
| `draft` | 작성 중, Agent 구현 금지 |
| `approved` | 구현·수정 허용 |
| `deprecated` | 대체 Spec 참조, 신규 구현 금지 |

**현재 스냅샷(2026-08-15):** 기존 코드베이스 역공학으로 작성된 초기 Spec 일괄 `approved`.

## 4. AI Agent 작업 프로토콜

### 4.1 작업 시작

1. 사용자 요청에서 **SPEC ID** 매핑 (`docs/specs/README.md` 인덱스)
2. 해당 Spec + **의존 Spec** + SSOT 링크 읽기
3. Spec에 없는 요구사항 → 사용자에게 Spec 추가 여부 확인

### 4.2 구현 중

- Spec의 FR/AC를 체크리스트로 사용
- 도메인 규칙 변경 시 `RunStateMachine`/`SuiteStateMachine` 등 **순수 계층** 우선
- AG-001~009 위반 금지 (`SPEC-PLATFORM-005`)

### 4.3 완료

1. AC별 검증 (단위 테스트 또는 수동 시나리오)
2. `python3 scripts/ci/run_all_gates.py --profile full`
3. Spec 변경이 있었다면 동일 PR에 포함

## 5. Spec 분해 원칙

- **한 Spec = 한 책임 영역** (예: OTP는 `SPEC-RUN-002`, Suite OTP는 `SPEC-SUITE-001`에 교차 참조)
- 시스템 E2E는 **시스템당 1 Spec** (`SPEC-SYS-*`); 모듈 단위 AC는 해당 Spec 내 섹션
- 300줄 초과 Spec은 하위 Spec으로 분할 검토

## 6. PR 체크리스트 (SDD 추가)

기존 `docs/DOCS_GOVERNANCE.md` PR 체크리스트에 더해:

- [ ] 동작 변경 시 관련 `docs/specs/**` 갱신
- [ ] 신규 기능에 SPEC ID 부여 (인덱스 README 반영)
- [ ] AC가 테스트 또는 수동 검증 절차와 연결됨

## 7. 기계 검증 vs 수동 검증

| 검증 대상 | 도구 | 비고 |
| --- | --- | --- |
| manifest ↔ 시나리오 ↔ 시스템 Spec `module_id` | `check_docs_consistency.py` | CI tier 0 |
| API·env·폴더 트리 | `check_docs_consistency.py` | CI tier 0 |
| 아키텍처 경계 (AG-001~009) | `check_architecture_gates.py` | CI tier 1 |
| Spec AC·Gherkin·UX 문구 | PR 리뷰·`@pytest.mark.spec`·수동 Run | **자동화 없음** |
| Spec 인덱스 링크·SPEC ID | `check_docs_consistency.py` | README ↔ 파일 실재 |
| Spec AC ↔ pytest | `tests/test_spec_traceability.py` | 마커가 Spec·AC 존재 검증 |

**주의:** `approved` 상태는 “역공학 초안 승인”이지 “모든 AC가 테스트로 증명됨”을 뜻하지 않는다. AC와 테스트 연결이 빈약한 Spec은 구현 작업 전 보강한다.

### 7.1 `@pytest.mark.spec` (SDD 추적성)

P0 Spec부터 수용 기준과 단위 테스트를 연결한다:

```python
@pytest.mark.spec("SPEC-RUN-001", "AC-002")
def test_post_step_rejects_input_not_declared_in_manifest(): ...
```

- `tests/test_spec_traceability.py`가 모든 마커가 실제 Spec 파일·`### AC-NNN` 섹션을 가리키는지 검증한다.
- 신규 AC 테스트 추가 시 Spec §9 테스트 요구사항 표도 함께 갱신한다.
- `pytest -m spec` 으로 마커 테스트만 실행 가능 (pytest 기본 `-m` 필터).
