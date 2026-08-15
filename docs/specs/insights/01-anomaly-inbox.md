# SPEC-INSIGHT-001: 이상징후 인박스

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-INSIGHT-001` |
| **상태** | `approved` |
| **구현** | `insights_anomalies.py`, `routes_anomalies.py`, `anomalies.js` |

## 1. UI

`GET /anomalies` — 사이드바 "이상징후"

## 2. API

| Method | Path |
| --- | --- |
| GET | `/api/anomalies` |
| GET | `/api/anomalies/assignees` |
| PATCH | `/api/anomalies/{module_run_id}` |

**데이터 소스:** `AnomalyInboxQueryPort` (list_runs 스캔 금지, AG-001)

## 3. FR-001: 인박스 항목

ANOMALY/FAILED 모듈 실행 — 시스템·모듈·시각·담당·처리 상태

## 4. FR-002: 처리

PATCH로 assignee, status, note 등 갱신 (`AnomalyHandlingStorePort`)

## 5. 스코프

non-admin: `allowed_system_codes`

## 6. 수용 기준

### AC-001: ERROR 제외

```gherkin
Given module finished ERROR
When GET /api/anomalies
Then not listed
```

### AC-002: ANOMALY 포함

```gherkin
Given module ANOMALY
When GET /api/anomalies
Then listed with module_run_id
```
