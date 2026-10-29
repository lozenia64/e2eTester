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

관리자 좌측 메뉴는 대시보드, Run 이력, 사용자 관리, 모듈 설정 순서로 4개만 표시한다.
운영 관측(`/admin/ops`)과 사용량 통계(`/admin/stats`)는 메뉴에서만 숨기며, 기존 URL 직접 접근과 API·기능은 유지한다.

### 사용자 관리 화면

- 상단 전체·활성·관리자 수, 이름/이메일 검색, 전체/활성/비활성 필터와 사용자 목록을 제공한다.
- 사용자 선택 시 우측 상세 패널에서 계정 정보·생성일·상태·시스템 권한을 확인한다. 좁은 화면에서는 목록 아래에 표시한다.
- 사용자 추가는 모달, 활성/비활성·삭제는 상세의 더보기 메뉴, 권한 저장은 패널 하단에 둔다. 기존 API를 유지한다.
- 관리자 계정의 시스템 권한은 전체 접근·읽기 전용이다. 계정 활성/삭제 기능은 기존대로 제공하며 작업 전 확인한다.
- 일반 계정의 `allowed_system_codes=[]`는 **접근 없음**이다. ‘전체 시스템’은 현재 등록된 시스템 코드를 명시적으로 모두 저장하며 이후 추가되는 시스템은 자동 허용하지 않는다. 미등록 기존 코드는 별도로 표시하고 명시적 해제 전까지 보존한다.
- 저장 중 중복 요청·사용자 전환을 막는다. 미저장 권한을 버릴 때 확인하며 실패 시 초안을 유지한다. 조회 실패는 빈 목록과 구분하고 재시도한다. 시스템 조회 실패 시 권한 편집을 잠근다.

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


### AC-004: 목록과 권한 편집

이름·이메일 검색은 대소문자를 구분하지 않고 상태 필터와 함께 적용한다. 필터 결과 건수와 전체 집계는 구분한다. 전체 시스템 저장은 빈 배열이 아닌 현재 코드 목록을 전송하고, 선택 0개 저장은 접근 없음으로 표시한다. 관리자·미등록 코드·HTML 문자가 있는 이름을 안전하게 표시한다.

### AC-005: 실패와 조작 보호

저장 실패는 오류와 미저장 초안을 보존한다. 저장 중 중복 제출·사용자 전환을 막으며 전환 취소 시 현재 사용자를 유지한다. 추가·활성/비활성·삭제 성공은 목록과 집계에 반영하고 추가 실패는 모달 입력을 유지한다. 모달은 키보드 포커스를 가두고 닫은 후 추가 버튼으로 복귀한다. 모바일 가로 넘침 없이 권한 상세에 접근할 수 있다.
