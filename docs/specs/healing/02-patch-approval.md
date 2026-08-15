# SPEC-HEAL-002: 패치 제안·승인

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-HEAL-002` |
| **상태** | `approved` |
| **의존** | `SPEC-HEAL-001` |
| **구현** | `patch_builder.py`, `routes_healing.py` |

## 1. 원칙

패치는 **human approval gate** — 자동 merge 금지.

## 2. FR-001: 패치 생성

성공/제안 heal → `PROPOSED` diff (`patch_builder.py`)

- quoted-literal replacement + unified diff
- dedupe: system + broken→healed pair
- tech-debt warnings

## 3. API

| Method | Path |
| --- | --- |
| GET | `/api/healing/patches` |
| POST | `/api/healing/patches/{id}/approve` |
| POST | `/api/healing/patches/{id}/reject` |
| GET | `/api/healing/patches/{id}/download` |

## 4. FR-002: Approve

소스 파일에 replacement 적용 (그 시점 literal). literal vanished → `409`.

Audit: `decided_by`, `decided_at`

## 5. FR-003: Reject

reason 기록

## 6. 수용 기준

### AC-001: 승인 시 파일 변경

```gherkin
Given PROPOSED patch for selector in page_objects/hom/foo.py
When approve
Then file contains healed selector literal
```

### AC-002: 409 on stale

```gherkin
Given source no longer contains broken literal
When approve
Then 409
```

## 7. 테스트

`tests/test_patch_builder.py`, `tests/test_healing_service.py`
