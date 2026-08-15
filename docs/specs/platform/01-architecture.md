# SPEC-PLATFORM-001: 플랫폼 아키텍처

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-PLATFORM-001` |
| **상태** | `approved` |
| **우선순위** | P0 |
| **의존** | — |
| **SSOT 링크** | `docs/E2E_ARCHITECTURE.md` §1–§5 |
| **구현 위치** | `app/composition/container.py`, `app/main.py` |

## 1. 개요

### 1.1 목적

FastAPI API 프로세스와 Playwright 실행 워커를 분리하고, 바운디드 컨텍스트·포트-어댑터 패턴으로 오케스트레이션과 실행·영속을 격리한다.

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `operator` | 대시보드에서 Run/Suite 실행 |
| `system` | 워커·스케줄러·OutboxRelay |
| `admin` | 관리자 화면·통계 |

### 1.3 범위

**In scope:**

- 실행 평면 분리·컨테이너 단일 배선·BC 경계·순수 도메인·읽기 프로젝션·import 경계

**Out of scope:**

- 개별 Run/Suite 상태 전이 (`SPEC-RUN-001`, `SPEC-SUITE-001`)
- ExecutionGateway 세부 (`SPEC-PLATFORM-003`)
- 이벤트 영속 (`SPEC-PLATFORM-002`)

## 2. 기능 요구사항 (FR)

### FR-001: 실행 평면 분리

API 프로세스(`app/main.py`)는 Playwright를 import·실행하지 않는다. 실브라우저 모듈은 `WorkerExecutionGateway` → `worker/http_server.py` → `SessionServer` 경로로만 실행된다.

- `E2E_EXECUTION_MODE=remote` + Redis 시 워커 필수
- `SIM` 모듈만 `SimulatedExecutionGateway`로 API 프로세스 내 실행 가능

### FR-002: 컴포지션 루트 단일화

모든 어댑터 배선은 `AppContainer.build(settings)` 한 곳에서만 수행한다. 라우트·WS 핸들러는 `app/api/dependencies.py`의 `Depends`로 서비스를 주입받으며 `app.state` 직접 접근 금지.

### FR-003: 바운디드 컨텍스트

| 컨텍스트 | 경로 | 책임 |
| --- | --- | --- |
| Run | `app/contexts/run/` | Run 생명주기·실행 루프·RunView |
| Suite | `app/contexts/suite/` | Suite 사가·SuiteView |
| Identity | `app/contexts/identity/` | 인증·사용자 |
| Scheduling | `app/contexts/scheduling/` | Cron·예약 |
| Healing | `app/contexts/healing/` | 셀렉터 자가 치유 |
| Insights | `app/contexts/insights/` | 운영 인텔리전스(읽기) |
| Preset | `app/contexts/preset/` | 인증 프리셋 |
| Execution | `app/execution/` | ExecutionGateway·큐 어댑터 |
| Realtime | `app/realtime/` | Outbox→WS 프로젝터 |
| Platform | `app/platform/` | 이벤트 버스·Outbox·공통 유틸 |
| Composition | `app/composition/` | `AppContainer` 조립 |
| Orchestrator (queries) | `app/orchestrator/queries/` | CQRS 읽기 핸들러(레거시 경로) |
| Automation | `app/automation/` | Flow + PageObject |
| Scenarios | `app/scenarios/` | 시스템별 Executor·Runtime |
| Runner | `app/runner/` | Playwright 실행 골격 |

### FR-004: 순수 도메인 규칙

`RunStateMachine`, `RunAggregate`, `SuiteStateMachine`, `SuiteAggregate`, `decider.evolve`는 `app/contexts/{run,suite}/domain/` 및 공유 `app/domain/`에 두며, `await`·repository·gateway import 없이 순수 함수로 유지한다. 서비스(`RunService`, `SuiteService`)는 **인터프리터**만 담당한다.

### FR-005: 읽기 모델 프로젝션

REST·WS 응답은 `RunView.dump` (`app/contexts/run/views/view.py`) / `SuiteView.dump` (`app/contexts/suite/views/view.py`)만 사용한다. 도메인 엔티티 `model_dump` 직접 직렬화 금지.

### FR-006: Import 경계

- `contexts/`·`api/` → `runner`/`automation`/`systems` import 금지 (AG-009)
- `app/orchestrator/` 및 `app/contexts/*/application/` → playwright import 금지 (AG-002)
- `app/domain/` 및 `app/contexts/*/domain/` → I/O·async 런타임 import 금지 (AG-003)

## 3. 수용 기준 (AC)

### AC-001: API 프로세스 Playwright 무-import

```gherkin
Given app/ 디렉터리 (worker/ 제외)
When import-linter 및 AG-002 검사 실행
Then app/orchestrator 및 app/contexts/*/application 에서 playwright import 없음
```

### AC-002: 컨테이너 단일 배선

```gherkin
Given AppContainer.build() 호출
When main.py lifespan 시작
Then RunService, SuiteService, gateways, repositories 가 container 에서만 생성됨
```

### AC-003: RunView 프로젝션

```gherkin
Given 완료된 Run
When GET /api/runs/{run_id}
Then 응답이 RunView.dump 경유이며 aggregate 직접 dump 아님
```

## 4. API 계약 (해당 시)

해당 없음 — 본 Spec은 구조·경계 정책이다. REST 목록은 `docs/E2E_ARCHITECTURE.md` §5.2.

## 5. 상태·이벤트 (해당 시)

해당 없음 — 도메인 이벤트는 `SPEC-PLATFORM-002`, WS는 `SPEC-PLATFORM-004`.

## 6. 데이터 모델 (해당 시)

해당 없음.

## 7. 엣지 케이스·오류 처리

| 상황 | 기대 동작 | HTTP/WS |
| --- | --- | --- |
| 컨테이너 미시작 lifespan | 서비스 미주입 | 500 / WS 거부 |
| import 경계 위반 | CI `architecture_gates`·`importlinter` 실패 | — |

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | 모듈 로그는 도메인 이벤트가 아님 — outbox 우회, 직접 WS (`SPEC-PLATFORM-004`) |
| NFR-002 | 부수 관심사(AI·메일)는 EventBus 구독자로만 연결 |
| NFR-003 | 오케스트레이션 계층은 Playwright 런타임 객체를 소유하지 않음 |

## 9. 테스트 요구사항

| AC | 유형 | 위치 | 내용 |
| --- | --- | --- | --- |
| AC-001 | CI 게이트 | `scripts/check_architecture_gates.py` (AG-002) | application 계층 playwright import 금지 |
| AC-001 | CI 게이트 | `importlinter` (`pyproject.toml`) | domain/orchestrator playwright 계약 |
| AC-002 | 단위 | `tests/test_container_lifecycle.py` | `AppContainer.build`·wire 순서·start/stop |
| AC-003 | 단위 | `tests/test_summary_queries.py` | RunView/요약 프로젝션 (간접) |
| — | CI 게이트 | `scripts/check_architecture_gates.py` (AG-009) | contexts/api → runner 금지 |

**수동:** 라이브 서버 기동 후 `/api/runs` 응답이 엔티티 raw dump가 아닌지 확인.

## 10. 구현 힌트 (참고)

| 구성요소 | 파일 |
| --- | --- |
| Composition root | `app/composition/container.py` |
| Lifespan | `app/main.py` |
| DI providers | `app/api/dependencies.py` |
| RunView | `app/contexts/run/views/view.py` |
| SuiteView | `app/contexts/suite/views/view.py` |

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 역공학 초안 | — |
| 2026-08-15 | `_TEMPLATE.md` 정합·테스트 매핑 | SDD 보강 |
