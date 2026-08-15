# SPEC-PLATFORM-004: 실시간 WebSocket

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-PLATFORM-004` |
| **상태** | `approved` |
| **우선순위** | P0 |
| **의존** | `SPEC-PLATFORM-002` |
| **SSOT 링크** | `docs/E2E_ARCHITECTURE.md` §2 (Outbox→WS) |
| **구현 위치** | `app/realtime/`, `app/api/ws_runs.py`, `app/api/ws_suites.py` |

## 1. 개요

### 1.1 목적

도메인 이벤트를 outbox → `RealtimeProjector` → WebSocket 단일 파이프라인으로만 대시보드에 전달한다.

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `operator` | Run/Suite 상세 화면 WS 구독 |
| `system` | OutboxRelay·RealtimeProjector·ListenerRegistry |

### 1.3 범위

**In scope:**

- WS 엔드포인트·이벤트 타입·페이로드·module_log 직행·Redis fan-out

**Out of scope:**

- 프론트 렌더링 상세 (`SPEC-UI-003`)
- 인증 정책 (`SPEC-IDENTITY-001`)

## 2. 기능 요구사항 (FR)

### FR-001: 엔드포인트

| Path | Auth | 초기 이벤트 |
| --- | --- | --- |
| `WS /ws/runs/{run_id}` | JWT 쿠키 | `snapshot` (RunView) |
| `WS /ws/suites/{suite_id}` | JWT 쿠키 + 활성 사용자 | `snapshot` (SuiteView) |

Bearer 토큰은 HTTP API용. WS는 쿠키만. 무효 토큰 → close `1008`.

### FR-002: Run 이벤트 타입

| event_type | 도메인 출처 |
| --- | --- |
| `snapshot` | 연결 시 |
| `run_created` | `RunCreated` |
| `run_started` | `RunStarted` |
| `run_finished` | `RunFinished` |
| `run_waiting_input` | `RunWaitingInput` |
| `run_resumed` | `RunResumed` |
| `module_queued` | `ModuleQueued`, `RunModuleRetried` |
| `module_started` | `ModuleStarted` |
| `module_finished` | `ModuleFinished`, `RunModuleBlocked`, ... |
| `module_waiting_input` | `RunWaitingInput` |
| `module_log` | **직접** (`_handle_module_log`, outbox 우회) |

### FR-003: Suite 이벤트 타입

`suite_created`, `suite_started`, `suite_step_started`, `suite_step_run_linked`, `suite_step_finished`, `suite_waiting_input`, `suite_resumed`, `suite_finished`

### FR-004: 페이로드 형태

`DashboardEvent { event_type, run_id, system_code, run_status, payload }` — fat event, blob 재수화 없음.

Suite: `SuiteEvent` + `SuiteView.dump_from_summary`.

### FR-005: 다중 API 프로세스

`RedisRealtimeFanout` (선택)으로 pub/sub fan-out.

### FR-006: 리스너 레지스트리

`ListenerRegistry`는 프로세스-로컬. 재기동 시 소멸.

## 3. 수용 기준 (AC)

### AC-001: 연결 스냅샷

```gherkin
Given RUNNING 상태 Run
When WS /ws/runs/{run_id} 연결
Then 첫 메시지 event_type=snapshot
And payload에 모든 모듈 현재 상태 포함
```

### AC-002: module_log 순서

```gherkin
Given 모듈 실행 중
When 로그 N줄 발생 후 module_finished
Then module_log N건이 module_finished 이전에 수신됨
```

### AC-003: PII 미포함

```gherkin
Given 휴대폰 인증 Run
When WS 이벤트 수신
Then phone_number, otp 등 PII 필드 없음
```

## 4. API 계약 (해당 시)

| Method | Path | Auth | Request | Response | 오류 |
| --- | --- | --- | --- | --- | --- |
| WS | `/ws/runs/{run_id}` | JWT 쿠키 | — | `DashboardEvent` JSON | close 1008 |
| WS | `/ws/suites/{suite_id}` | JWT 쿠키 | — | `SuiteEvent` JSON | close 1008 |

## 5. 상태·이벤트 (해당 시)

### 5.2 WebSocket 이벤트

FR-002·FR-003 표 참조. `module_log`만 outbox 우회.

## 6. 데이터 모델 (해당 시)

```text
DashboardEvent — app/realtime/events.py (또는 adapter)
RunView / SuiteView — 프로젝션 payload
```

## 7. 엣지 케이스·오류 처리

| 상황 | 기대 동작 | HTTP/WS |
| --- | --- | --- |
| 쿠키 없음/만료 | 연결 거부 | WS close 1008 |
| 프로세스 재기동 | 리스너 소멸 — 클라이언트 재연결 | — |
| Redis fan-out 비활성 | 단일 프로세스 로컬 브로드캐스트 | — |

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | 오케스트레이터가 repo에서 직접 WS publish 금지 |
| NFR-002 | WS payload에 PII·OTP 미포함 |
| NFR-003 | module_log는 고빈도 — outbox 부하 방지 |

## 9. 테스트 요구사항

| AC | 유형 | 위치 | 내용 |
| --- | --- | --- | --- |
| AC-002 | 단위 | `tests/test_module_log_pipeline.py` | 로그→realtime, 이벤트 스토어 미경유 |
| AC-002 | 단위 | `tests/test_outbox_relay_hydration.py` | projector·outbox 경로 |
| AC-003 | 단위 | `tests/test_module_log_pipeline.py` | payload에 입력 PII 없음 (간접) |
| — | 단위 | `tests/test_realtime_fanout_wiring.py` | Redis fan-out 배선 |
| — | 단위 | `tests/test_outbox_relay_dedup.py` | relay 중복 방지 |

**수동:** 브라우저 WS 연결·snapshot·OTP 패널 (`SPEC-UI-003`).

## 10. 구현 힌트 (참고)

| 구성요소 | 파일 |
| --- | --- |
| Projector | `app/realtime/projector.py` |
| Adapter | `app/realtime/adapter.py` |
| Run WS | `app/api/ws_runs.py` |
| Suite WS | `app/api/ws_suites.py` |
| Front-end | `app/web/static/app.js` |

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 역공학 초안 | — |
| 2026-08-15 | `_TEMPLATE.md` 정합·테스트 매핑 | SDD 보강 |
