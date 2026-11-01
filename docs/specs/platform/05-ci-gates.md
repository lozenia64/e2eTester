# SPEC-PLATFORM-005: CI·아키텍처 게이트

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-PLATFORM-005` |
| **상태** | `approved` |
| **우선순위** | P0 |
| **의존** | `SPEC-PLATFORM-001` |
| **SSOT 링크** | `docs/CI.md` |
| **구현 위치** | `scripts/ci/gates.py`, `scripts/check_architecture_gates.py`, `scripts/check_docs_consistency.py` |

## 1. 개요

### 1.1 목적

PR 병합 전 자동 검증 게이트로 아키텍처·문서·단위 테스트 회귀를 차단한다. 라이브 Playwright E2E는 CI 밖(수동).

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `system` | GitHub Actions·`run_all_gates.py` |
| `operator` | PR 전 로컬 게이트 실행 |

### 1.3 범위

**In scope:**

- Tier 게이트·AG-001~009·docs consistency·pytest·조건부 security gates

**Out of scope:**

- 라이브 사이트 E2E·cross-restart OTP (수동 게이트)

## 2. 기능 요구사항 (FR)

### FR-001: 게이트 계층

게이트 정의의 SSOT는 `scripts/ci/gates.py`다. Tier별 목록·로컬/CI 실행 명령과 커버리지 기준은 [docs/CI.md](../../CI.md)를 참조한다.

### FR-002: 아키텍처·프론트엔드 게이트 (AG / FG)

아키텍처 게이트(`AG-001~009`, `scripts/check_architecture_gates.py`) 및 프론트엔드 게이트(`FG-001~007`, `scripts/check_frontend_gates.py`)의 규칙 상세는 [docs/CI.md](../../CI.md)를 참조한다.

### FR-003: 문서 정합성 가드

`check_docs_consistency.py` 검증:

- manifest ↔ `docs/scenarios/{code}.md` 1:1·module_id
- manifest ↔ `docs/specs/systems/{code}.md` 1:1·module_id
- `docs/specs/README.md` 인덱스 ↔ Spec 파일 양방향 등재 및 ID 메타데이터 일치(섹션 앵커가 있는 링크도 파일 경로로 대조)
- API ↔ `E2E_ARCHITECTURE.md` §5.2 양방향
- 프로젝트 환경변수(`E2E_*`/`GEMINI_*`) ↔ INSTALL/.env.example 양방향(코드 변수는 두 문서 각각에 등재)
- §4 폴더 트리 실재 및 주요 디렉터리 항목의 역방향 등재
- CI 게이트 및 AG/FG 규칙 ID의 CI 문서 등재

**Spec AC·Gherkin·행동 서술은 기계 검증 대상이 아니다** — PR 리뷰·`@pytest.mark.spec`·수동 시나리오.

## 3. 수용 기준 (AC)

### AC-001: PR 게이트 통과

```gherkin
Given main 브랜치 대비 변경
When run_all_gates.py --profile full
Then exit code 0
```

### AC-002: manifest 변경 동기화

```gherkin
Given manifest.yaml 모듈 추가
When docs_consistency 실행
Then 대응 scenarios/{code}.md 및 specs/systems/{code}.md 에 동일 module_id 존재
Otherwise FAIL
```

### AC-003: Spec 인덱스 무결성

```gherkin
Given docs/specs/README.md 인덱스
When docs_consistency 실행
Then docs/specs/ 내부의 모든 .md 링크 대상 파일이 존재하고 모든 Spec 파일이 인덱스에 등재됨
And 섹션 앵커가 있는 링크도 동일한 파일로 인식함
And 인덱스 ID는 대상 Spec의 ID 메타데이터와 일치함 (의존 Spec 언급으로 대체 불가)
And 행동 Spec마다 ID 인덱스 행이 정확히 하나이고 ID 중복이 없음 (거버넌스·템플릿은 ID 없이 링크만 등록)
```

### AC-004: 환경변수·폴더·게이트 문서 누락 차단

```gherkin
Given 프로젝트 환경변수 또는 주요 디렉터리 항목 또는 CI 게이트·AG/FG 규칙 ID 변경
When docs_consistency 실행
Then 환경변수는 INSTALL과 .env.example 각각에서 확인됨
And 주요 디렉터리 항목은 아키텍처 §4 트리에서 확인됨
And CI 게이트·규칙 ID는 CI 문서에서 확인됨
Otherwise FAIL
```

## 4. API 계약 (해당 시)

해당 없음.

## 5. 상태·이벤트 (해당 시)

해당 없음.

## 6. 데이터 모델 (해당 시)

해당 없음.

## 7. 엣지 케이스·오류 처리

| 상황 | 기대 동작 |
| --- | --- |
| 게이트 하나 실패 | exit code 1, 실패 목록 출력 |
| `docs_only` profile | docs + architecture만 실행 |
| security gates | auth/PII 변경 또는 주간 스케줄 |

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | `scripts/ci/gates.py`가 게이트 SSOT |
| NFR-002 | 로컬·CI 동일 명령 (`run_all_gates.py`) |
| NFR-003 | 라이브 브라우저 테스트는 CI 필수 아님 |

## 9. 테스트 요구사항

| AC | 유형 | 위치 | 내용 |
| --- | --- | --- | --- |
| AC-001 | CI | `scripts/ci/run_all_gates.py --profile full` | 전체 게이트 |
| AC-002 | CI | `scripts/check_docs_consistency.py` | manifest↔문서 |
| AC-003 | 단위·CI | `tests/test_docs_consistency.py`, `scripts/check_docs_consistency.py` | 인덱스 양방향·ID 메타데이터·섹션 앵커 링크·ID 누락/중복 차단 |
| AC-004 | CI | `scripts/check_docs_consistency.py` | 환경변수 양쪽 등재·주요 디렉터리·게이트 규칙 등재 |
| — | CI | `scripts/check_architecture_gates.py` | AG-001~009 |
| — | CI | `importlinter` | import 계약 |
| — | CI | `pytest tests/ -q` | 단위 회귀 |

## 10. 구현 힌트 (참고)

| 구성요소 | 파일 |
| --- | --- |
| Gate SSOT | `scripts/ci/gates.py` |
| Architecture | `scripts/check_architecture_gates.py` |
| Docs | `scripts/check_docs_consistency.py` |
| CI workflow | `.github/workflows/ci.yml` |

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 역공학 초안 | — |
| 2026-08-15 | Spec 인덱스 가드·템플릿 정합 | SDD 보강 |
