# SPEC-PLATFORM-003: ExecutionGateway·워커

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-PLATFORM-003` |
| **상태** | `approved` |
| **우선순위** | P0 |
| **의존** | `SPEC-PLATFORM-001`, `SPEC-RUN-003` |
| **SSOT 링크** | `docs/E2E_ARCHITECTURE.md` §2 |
| **구현 위치** | `app/execution/`, `worker/` |

## 1. 개요

### 1.1 목적

오케스트레이션과 브라우저 실행을 `ExecutionGateway` 포트로 분리해 API 프로세스가 Playwright를 직접 다루지 않게 한다.

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `system` | SessionServer·워커 HTTP·ThreadPoolExecutor |
| `operator` | Run 시작으로 간접 호출 |

### 1.3 범위

**In scope:**

- Gateway 포트·composite 라우팅·워커 HTTP·스레드 모델·공유 세션·모바일 모드·치유·step 로깅

**Out of scope:**

- Run 상태머신 (`SPEC-RUN-001`)
- 자가 치유 정책 상세 (`SPEC-HEAL-001`)

## 2. 기능 요구사항 (FR)

### FR-001: Gateway 포트

| 메서드 | 설명 |
| --- | --- |
| `open_session(run_id, system_code, input, storage_state?)` | 브라우저 세션 생성 |
| `run_step(handle, module_def, input, log_cb)` | 단일 모듈 실행 |
| `submit_input(handle, otp_code)` | OTP 제출 |
| `resume_from_step(handle, module_def, input, log_cb)` | 부분 재실행 |
| `capture_storage_state(handle)` | 체크포인트 캡처 |
| `close_session(handle)` | 세션 종료 |

`RunService`는 `ExecutionHandle`만 보유 — Playwright 객체 직접 접근 금지.

### FR-002: Composite 라우팅

`CompositeExecutionGateway`가 `execution_mode`별 어댑터 선택:

- `hom_workflow_step` 등 → `WorkerExecutionGateway` (또는 Local)
- `simulated` → `SimulatedExecutionGateway`

### FR-003: 워커 HTTP API

`worker/http_server.py` 엔드포인트:

- `POST /sessions` — open
- `POST /sessions/{id}/steps` — run_step
- `POST /sessions/{id}/submit-input` — OTP
- `POST /sessions/{id}/resume-from-step` — 부분 재실행
- `DELETE /sessions/{id}` — close

### FR-004: 스레드 모델

`SessionServer`는 세션당 `ThreadPoolExecutor(max_workers=1)`. Playwright sync API는 생성 스레드에서만 호출.

로그 브리지: `loop.call_soon_threadsafe(queue.put_nowait)` — 브라우저 스레드 블로킹 금지. `run_step` 종료 전 drain 완료 대기.

### FR-005: 공유 브라우저 세션

Run 내 모든 모듈은 동일 context/page 재사용. OTP 일시정지 시에도 in-process 세션 유지.

### FR-006: 모바일 디바이스 모드

`ChannelProfile.mobile=True` 시 `apply_mobile_device_mode()` 후 navigate (MHM, CHBOT).

### FR-007: 자가 치유

`BaseWorkflowExecutor._dispatch_with_healing`이 step 예외 시 `SelfHealingEngine` 호출. 성공 시 1회 재시도. `HealedPage` 프록시로 오버라이드 적용.

### FR-008: Step 로깅

`contextvars` 기반 per-step sink (`app/runner/step_logging.py`). `print`/`redirect_stdout` 금지 (AG-006).

## 3. 수용 기준 (AC)

### AC-001: API Playwright 무실행

```gherkin
Given E2E_EXECUTION_MODE=remote
When Run 시작
Then API 프로세스에 Playwright 프로세스 없음
And worker 프로세스에서 Chromium 기동
```

### AC-002: 동시 스텝 로그 격리

```gherkin
Given 동시 2 Run 실행
When 각 모듈이 ctx.log 호출
Then 모듈 A 로그가 모듈 B execution.log/WS에 섞이지 않음
```

### AC-003: resume-from-step

```gherkin
Given terminal Run 과 live 세션 없음
When POST /api/runs/{id}/rerun?from_module=hom.contract.list
And partial_rerun_allowed=true
Then gateway.resume_from_step 으로 동일 run_id 재개
```

## 4. API 계약 (해당 시)

워커 내부 HTTP — `worker/http_server.py`. 대시보드 REST는 `SPEC-RUN-002`.

## 5. 상태·이벤트 (해당 시)

해당 없음 — 실행 결과는 `StepExecutionResult`로 Run 서비스에 반환.

## 6. 데이터 모델 (해당 시)

```text
ExecutionHandle — app/execution/gateway.py (직렬화 가능 핸들)
```

## 7. 엣지 케이스·오류 처리

| 상황 | 기대 동작 | HTTP/WS |
| --- | --- | --- |
| 워커 다운 (remote) | Run ERROR/재시도 | 502/내부 예외 |
| step 타임아웃 | 모듈 ERROR/ANOMALY 분류 | — |
| healing 실패 | 원본 Playwright 예외 보존 | — |

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | 세션 스레드 단일 — Playwright sync API 규칙 준수 |
| NFR-002 | 아티팩트 `artifacts/{run_id}/{module_id}/execution.log`, `final.png` |
| NFR-003 | AG-006 — 전역 stdout 치환 금지 |

## 9. 테스트 요구사항

| AC | 유형 | 위치 | 내용 |
| --- | --- | --- | --- |
| AC-001 | 수동 | 라이브 remote 모드 | API 프로세스 Playwright 부재 |
| AC-002 | 단위 | `tests/test_step_context.py` | ctx.log·sink 격리 |
| AC-002 | 단위 | `tests/test_module_log_pipeline.py` | 로그 파이프라인 |
| AC-003 | 단위 | `tests/test_run_state_machine.py` | `decide_partial_rerun` |
| AC-003 | 통합 | `tests/test_run_checkpoint_integration.py` | checkpoint resume 경로 |
| — | 단위 | `tests/test_session_server.py` | SessionServer 스레드·세션 |
| — | 단위 | `tests/test_worker_gateway_errors.py` | 워커 오류 매핑 |
| — | CI 게이트 | `scripts/check_architecture_gates.py` (AG-006) | print/redirect_stdout 금지 |

## 10. 구현 힌트 (참고)

| 구성요소 | 파일 |
| --- | --- |
| Gateway port | `app/execution/gateway.py` |
| Composite | `app/execution/composite_gateway.py` |
| Session server | `worker/session_server.py` |
| Step logging | `app/runner/step_logging.py` |
| Worker HTTP | `worker/http_server.py` |

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 역공학 초안 | — |
| 2026-08-15 | `_TEMPLATE.md` 정합·테스트 매핑 (존재하지 않던 `test_local_gateway_session.py` 제거) | SDD 보강 |
