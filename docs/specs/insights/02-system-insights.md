# SPEC-INSIGHT-002: 시스템 인사이트

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-INSIGHT-002` |
| **상태** | `approved` |
| **구현** | `insights_service.py`, `routes_insights.py`, `insights.js` |

## 1. UI

- `GET /insights` — 시스템 목록
- `GET /systems/{system_code}/insights` — per-system

## 2. API

| Method | Path | 빌더 |
| --- | --- | --- |
| GET | `/api/systems/{code}/health` | `insights_health.py` |
| GET | `/api/systems/{code}/timeline` | `insights_timeline.py` |
| GET | `/api/systems/{code}/modules/breakdown` | `insights_breakdown.py` |

Plotly figure JSON via `insights_charts.py`

## 3. 내용

- **Health:** 최근 성공률, 연속 실패, SLA 유사 지표
- **Timeline:** 수직 타임라인 (run/module 이벤트)
- **Breakdown:** 모듈별 실패·소요 분포

## 4. 수용 기준

### AC-001: 접근 제어

```gherkin
Given user without hrp access
When GET /api/systems/hrp/health
Then 403
```

### AC-002: 프로젝션 기반

```gherkin
Given anomaly in projection index
When health API
Then reflects without full blob load
```
