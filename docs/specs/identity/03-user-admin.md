# SPEC-IDENTITY-003: 사용자 관리 (Admin)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-IDENTITY-003` |
| **상태** | `approved` |
| **의존** | `SPEC-IDENTITY-001`, `SPEC-IDENTITY-002` |
| **구현** | `app/api/routes_admin.py`, `UserService` |

## 1. API (모두 `require_admin`)

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/admin/users` | 전체 사용자 목록 |
| POST | `/api/admin/users` | 사용자 생성 `201` |
| PATCH | `/api/admin/users/{id}/active` | 활성/비활성 |
| DELETE | `/api/admin/users/{id}` | 삭제 |
| PUT | `/api/admin/users/{id}/systems` | 시스템 접근 설정 |
| GET | `/api/admin/systems` | 할당 가능 시스템 목록 |

### FR-001: 사용자 생성

**Body:** `CreateUserRequest { email, name, password, role? }`

| 규칙 | 값 |
| --- | --- |
| user_id | `usr_{8hex}` 자동 |
| role 기본 | `user` |
| 중복 email | `409` |

### FR-002: 미구현

- 이메일/이름/role 일괄 수정 API 없음
- 관리자 타인 비밀번호 재설정 API 없음

## 2. Admin HTML 페이지

| Path | Template |
| --- | --- |
| `/admin` | 관제 대시보드 (7일 커버리지) |
| `/admin/runs` | Run 이력 |
| `/admin/users` | 사용자 관리 |
| `/admin/modules` | 모듈 수동 업무 시간 |
| `/admin/ops` | 운영 관측 |
| `/admin/stats` | 사용량 통계 |

## 3. 수용 기준

### AC-001: 사용자 생성

```gherkin
Given admin 세션
When POST /api/admin/users {email, name, password}
Then 201 UserPublic
And role=user by default
```

### AC-002: 비관리자 차단

```gherkin
Given user role
When GET /api/admin/users
Then 403
```

### AC-003: 비활성화

```gherkin
Given PATCH active=false
When 해당 사용자 로그인 시도
Then 실패 (authenticate returns None)
```
