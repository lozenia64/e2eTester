# SPEC-UI-001: 일간 점검 현황 대시보드

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-UI-001` |
| **상태** | `approved` |
| **의존** | `SPEC-IDENTITY-002` |
| **구현** | `app/web/templates/dashboard.html`, `app/web/static/dashboard.js`, `app/contexts/insights/application/daily_dashboard.py` |

## 1. 개요

로그인 후 **첫 화면** (`GET /`). 오늘(KST) per-system/per-module 점검 상태.

## 2. API

| Method | Path |
| --- | --- |
| GET | `/api/dashboard/daily` |
| GET | `/api/dashboard/daily/fragments/{zone}` |
| GET | `/api/dashboard/daily/fragments/system/{code}/panel` |

**스코프:** 사용자 `allowed_system_codes`. PII-free.

## 3. UI

> **UI 리디자인:** 시각·레이아웃은 `SPEC-UI-004`~`008`이 SSOT. **무스크롤·압축 수납**은 `SPEC-UI-007` 최우선. **사이드바 인셋**은 `SPEC-UI-008`. API·집계는 본 Spec 유지.

- 30초 auto-refresh
- admin은 `/` 접근 시 `/admin` 리다이렉트

## 4. 수용 기준

### AC-001: 오늘만

```gherkin
Given E2E_SCHEDULE_TZ=Asia/Seoul
When GET /api/dashboard/daily at 23:59 KST
Then only today's runs reflected
```

### AC-002: 스코프

```gherkin
Given user allowed ["hom"]
When GET daily
Then mhm modules absent
```

## 5. 테스트

`tests/test_daily_dashboard.py` — daily_dashboard builder 단위
