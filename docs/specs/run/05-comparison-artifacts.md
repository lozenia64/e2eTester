# SPEC-RUN-005: Run 비교·아티팩트·로그

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-RUN-005` |
| **상태** | `approved` |
| **의존** | `SPEC-RUN-001`, `SPEC-PLATFORM-004` |

## 1. RunComparator

**시점:** `_finalize_run` 내 `finalize()` 전

**Baseline:** 동일 `system_code`의 `requested_at` 이전 최근 finished run (`RunSummaryQueryPort.find_previous_finished_run_id`)

**모듈별 분류 (non-SKIPPED):**

| Current | Baseline | Bucket |
| --- | --- | --- |
| ANOMALY/FAILED | not anomaly | `newly_failed` |
| ANOMALY/FAILED | anomaly | `still_failing` |
| PASSED | anomaly | `recovered` |

별도 baseline 테이블 없음 — 매 finalize 시 재계산.

**WS:** `run_finished` payload에 comparison 포함

## 2. 아티팩트

경로: `artifacts/{run_id}/{module_id}/`

| 파일 | 설명 |
| --- | --- |
| `execution.log` | 모듈 실행 로그 |
| `final.png` | 종료 스크린샷 |

진단 컨텍스트: `current_url`, `dialog_messages`, screenshot path — 실패 분석·AI용

## 3. 모듈 로그

- 저장: `RunLogStorePort` append-only
- 스트리밍: WS `module_log` (outbox 우회)
- 읽기: `get_run` hydration

**불변:** `run_step` 완료 전 모든 로그 drain 완료

## 4. 수용 기준

### AC-001: comparison 첨부

```gherkin
Given 이전 run ANOMALY, 현재 PASSED
When finalize
Then comparison.recovered 에 해당 모듈 포함
```

### AC-002: 아티팩트 생성

```gherkin
Given 모듈 실행 완료
When artifacts 디렉터리 확인
Then execution.log, final.png 존재
```

### AC-003: 로그 WS

```gherkin
Given 모듈 RUNNING
When step이 ctx.log 호출
Then module_log 이벤트 실시간 수신
```

## 5. 관련

- `SPEC-INT-003` AI가 diagnostic context 소비
