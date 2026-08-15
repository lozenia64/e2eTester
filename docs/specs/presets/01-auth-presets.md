# SPEC-PRESET-001: 인증 프리셋 (내 점검 세트)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-PRESET-001` |
| **상태** | `approved` |
| **구현** | `app/contexts/preset/`, `routes_presets.py` |

## 1. 개요

사용자별 named preset: auth method + inputs + selected modules. **PII 의도적 영속**.

## 2. API

| Method | Path |
| --- | --- |
| GET | `/api/presets` |
| POST | `/api/presets` |
| PUT | `/api/presets/{preset_id}` |
| DELETE | `/api/presets/{preset_id}` |

**Page:** `GET /presets` → `presets.html` (`presets.js`)

## 3. FR-001: 격리

- owner만 CRUD·`input_data` 조회
- `validate_run_request` 통과 조합만 저장

## 4. FR-002: Execute 연동

- 시스템 카드: preset chip 클릭 → 폼 채움
- SUITE: 시스템별 preset 선택 필수

## 5. 수용 기준

### AC-001: 타인 접근 불가

```gherkin
Given preset owned by user A
When user B PUT /api/presets/{id}
Then 404 or 403
```

### AC-002: 검증

```gherkin
Given invalid module selection
When POST preset
Then 400
```

## 6. 저장

`auth_presets` SQLite table, `SqlitePresetRepository`
