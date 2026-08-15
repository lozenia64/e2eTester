# SPEC-IDENTITY-002: 인가 (Authorization)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-IDENTITY-002` |
| **상태** | `approved` |
| **의존** | `SPEC-IDENTITY-001` |

## 1. 역할 모델

| role | 값 | 권한 |
| --- | --- | --- |
| admin | `admin` | 전체 시스템·전체 Run·관리자 UI·글로벌 healing policy |
| user | `user` | `allowed_system_codes` 범위만 |

`require_admin` 실패 → `403 "관리자 권한이 필요합니다."`

## 2. 시스템 접근 스코프

**필드:** `User.allowed_system_codes: list[str]`

| 역할 | 쿼리 스코프 |
| --- | --- |
| admin | `None` = 전체 시스템 |
| user | 목록 내 코드만; 빈 목록 = 접근 없음 |

**관리:** `PUT /api/admin/users/{user_id}/systems` body `{"allowed_system_codes": [...]}`

## 3. 적용 지점

| 영역 | 규칙 |
| --- | --- |
| Run 시작 | `system_code ∉ allowed` → 403 |
| Suite 시작 | `resolve_suite_request_for_user` |
| Preset | create/update 시 `_ensure_system_access` |
| Schedule | per-system 생성·캘린더 스코프 |
| Daily dashboard | `allowed_system_codes` 필터 |
| Insights | per-system 403 |
| Anomalies | 쿼리 스코프 |
| Healing | non-admin은 허용 시스템만; `*` policy는 admin |
| Execute page | 시스템 카드 서버 필터 |
| Run list | non-admin: `user_id` = 본인만 |

## 4. 관리자 UI 리다이렉트

admin이 다음 접근 시 리다이렉트:
- `/` → `/admin`
- `/runs/execute`, `/runs/history` → `/admin` 또는 `/admin/runs`

**예외 (리다이렉트 없음):** `/presets`, `/schedules`, `/self-healing`, `/anomalies`, `/insights`

## 5. 인증 예외

| 기능 | Auth |
| --- | --- |
| `GET /api/systems` | **없음** — 전체 manifest 목록 |
| `GET /m/{trigger_token}` | 토큰만 |
| `POST /api/trigger/{token}` | 토큰만 |

## 6. 수용 기준

### AC-001: 시스템 스코프

```gherkin
Given user with allowed_system_codes=["hom"]
When POST /api/runs/systems/mhm
Then 403
```

### AC-002: Run 목록 격리

```gherkin
Given user A, user B 각각 Run 생성
When user A가 GET /api/runs
Then user B Run 미포함
```

### AC-003: Admin 전체 조회

```gherkin
Given admin
When GET /api/admin/runs
Then 모든 사용자 Run 포함
```
