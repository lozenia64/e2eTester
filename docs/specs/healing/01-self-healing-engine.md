# SPEC-HEAL-001: 자가 치유 엔진

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-HEAL-001` |
| **상태** | `approved` |
| **구현** | `app/contexts/healing/engine.py`, `healing.js` |

## 1. UI

`GET /self-healing` — 사이드바 badge (pending patch count)

## 2. 런타임 파이프라인

step 예외 → `_dispatch_with_healing`:

1. `selector_healer` — Playwright 오류에서 broken selector 파싱
2. live DOM fingerprint 스캔·스코어링
3. top candidate live verify
4. confidence ≥ threshold → runtime override + **1회** 재시도
5. 미만 → pending suggestion only

## 3. FR-001: Confidence 게이트

정책: per-system → global `*` → default **0.75**

`SqliteHealingPolicyReader` (sync, 5s TTL on execution thread)

## 4. FR-002: HealedPage

`runtime.page` → proxy during module. 이미 override된 selector 재치유 금지 (loop guard).

## 5. FR-003: 기록

`StepExecutionResult.healing_events` → `HealingService` → SQLite

## 6. API (읽기)

| Method | Path |
| --- | --- |
| GET | `/api/healing/events` |
| GET | `/api/healing/metrics` |
| GET | `/api/healing/durability` |
| GET/PUT | `/api/healing/policy` |

**metrics:** month auto-recovered, unattended rate, MTTR, chronic promotion (3+ heals)

**durability:** steps 소스 정적 스캔 + heal history → risk ranking

## 7. 스코프

non-admin: `allowed_system_codes`. global `*` policy PUT은 admin only.

## 8. 수용 기준

### AC-001: 치유 실패 시 원본 예외

```gherkin
Given healing engine throws
When step failed
Then original Playwright error preserved
```

### AC-002: 비셀렉터 오류

```gherkin
Given timeout not selector-related
When healing invoked
Then no override, fail as-is
```

## 9. 테스트

`tests/test_selector_healer.py`, `tests/test_healing_engine.py`, `tests/test_healing_metrics.py`
