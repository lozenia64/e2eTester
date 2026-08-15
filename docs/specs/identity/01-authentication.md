# SPEC-IDENTITY-001: 인증 (Authentication)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-IDENTITY-001` |
| **상태** | `approved` |
| **우선순위** | P0 |
| **의존** | — |
| **SSOT 링크** | `docs/INSTALL.md` (JWT env), `docs/E2E_ARCHITECTURE.md` §5.2 (/auth) |
| **구현 위치** | `app/contexts/identity/`, `app/auth/router.py` |

## 1. 개요

### 1.1 목적

JWT 기반 세션·로그인·비밀번호 변경·부트스트랩 관리자를 정의한다. HTTP는 Bearer 또는 `access_token` 쿠키. WebSocket은 쿠키만.

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `operator` | 로그인·비밀번호 변경 |
| `admin` | 부트스트랩 계정 (env) |
| `system` | `seed_admin` lifespan |

### 1.3 범위

**In scope:**

- 로그인/로그아웃·JWT·쿠키·`/auth/me`·비밀번호 변경·인증 실패 처리

**Out of scope:**

- 역할·시스템 스코프 (`SPEC-IDENTITY-002`)
- 사용자 CRUD (`SPEC-IDENTITY-003`)

## 2. 기능 요구사항 (FR)

### FR-001: 로그인

**API:** `POST /auth/login` (Form: `email`, `password`)

| 결과 | 동작 |
| --- | --- |
| 성공 | JWT + `access_token` 쿠키 |
| 실패 | `303 /login?error=1` |
| 비활성 | 실패와 동일 |

Content negotiation: `Accept: application/json` → `200 TokenResponse`; 그 외 → `303 /`

### FR-002: JWT·쿠키

| 설정 | 값 |
| --- | --- |
| Secret | `E2E_JWT_SECRET` |
| Algorithm | HS256 |
| TTL | 7일 |
| Cookie | httponly, samesite=lax, max_age=604800 |

### FR-003: 로그아웃

`POST /auth/logout` — 쿠키 삭제 → `/login`

### FR-004: 현재 사용자

`GET /auth/me` → `UserPublic`

### FR-005: 비밀번호

- Argon2id (`pwdlib`); 레거시 bcrypt → 로그인 시 재해시
- `POST /auth/change-password` — mismatch/wrong/weak 리다이렉트

### FR-006: 부트스트랩

`seed_admin(E2E_ADMIN_EMAIL, E2E_ADMIN_PASSWORD)` — 이메일 없을 때만

### FR-007: 인증 실패

| 경로 | 동작 |
| --- | --- |
| `/api/*` | `401` JSON |
| HTML | `RedirectResponse("/login")` |

## 3. 수용 기준 (AC)

### AC-001: 쿠키 로그인

```gherkin
Given 유효한 email/password
When POST /auth/login (HTML)
Then Set-Cookie access_token
And 303 redirect /
```

### AC-002: 비활성 계정

```gherkin
Given is_active=false 사용자
When GET /api/runs (유효 JWT)
Then 401 "비활성화된 계정입니다."
```

### AC-003: WS 인증

```gherkin
Given access_token 쿠키 없음
When WS /ws/runs/{id} 연결
Then close code 1008
```

## 4. API 계약 (해당 시)

| Method | Path | Auth | Request | Response | 오류 |
| --- | --- | --- | --- | --- | --- |
| POST | `/auth/login` | — | Form email/password | 303 or TokenResponse | 303 error |
| POST | `/auth/logout` | — | — | 303 /login | — |
| GET | `/auth/me` | JWT | — | UserPublic | 401 |
| POST | `/auth/change-password` | JWT | Form | redirect/json | redirect error |
| GET | `/login` | — | — | HTML | — |

## 5. 상태·이벤트 (해당 시)

해당 없음.

## 6. 데이터 모델 (해당 시)

```text
User / UserPublic — app/contexts/identity/
SqliteUserRepository — app/contexts/identity/infrastructure/
```

## 7. 엣지 케이스·오류 처리

| 상황 | 기대 동작 | HTTP |
| --- | --- | --- |
| 잘못된 비밀번호 | 동일 실패 UX (타이밍 주의) | 303 error |
| 만료 JWT | 401 / login redirect | 401 |
| change-password weak | `?error=weak` | 303 |

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | `hashed_password`는 API 응답에 미포함 |
| NFR-002 | JWT secret 미설정 시 기본값은 개발 전용 |
| NFR-003 | WS는 Bearer 미지원 — 쿠키만 |

## 9. 테스트 요구사항

| AC | 유형 | 위치 | 내용 |
| --- | --- | --- | --- |
| AC-001 | 수동 | 브라우저 `/login` | 쿠키·리다이렉트 |
| AC-002 | 수동 | API + 비활성 사용자 | 401 메시지 |
| AC-003 | 수동 | WS without cookie | close 1008 |
| — | 단위 | `tests/test_input_crypto.py` | 암호화 유틸 (간접) |
| — | 단위 | `tests/test_settings.py` | JWT env 파싱 |
| — | CI | `bandit_security` (auth 경로) | 보안 스캔 |

**후속:** `tests/test_auth_http.py` HTTP 테스트 추가 권장.

## 10. 구현 힌트 (참고)

| 구성요소 | 파일 |
| --- | --- |
| Auth router | `app/auth/router.py` |
| Identity service | `app/contexts/identity/service.py` |
| Login template | `app/web/templates/login.html` |
| WS auth | `app/api/ws_runs.py`, `app/api/ws_suites.py` |

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 역공학 초안 | — |
| 2026-08-15 | `_TEMPLATE.md` 정합·테스트 매핑 (HTTP 테스트 공백 명시) | SDD 보강 |
