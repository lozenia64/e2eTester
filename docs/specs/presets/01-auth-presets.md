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
- 예약: 선택한 프리셋 ID를 저장하며 다음 실행 시작 시 최신 인증값을 사용한다.
  프리셋 적용 후 폼의 인증값을 바꾸면 먼저 프리셋으로 저장하도록 안내한다.
  연결된 예약의 인증값은 프리셋 관리에서 변경하고, 실행 대상 모듈·브라우저 설정은 예약에 유지한다.

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
