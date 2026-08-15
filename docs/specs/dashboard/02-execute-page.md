# SPEC-UI-002: 점검 실행 페이지

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-UI-002` |
| **상태** | `approved` |
| **의존** | `SPEC-RUN-001`, `SPEC-SUITE-001`, `SPEC-PRESET-001` |

## 1. 페이지

`GET /runs/execute` → `execute.html`

## 2. 구성

### FR-001: SUITE 카드

- 전체 시스템 순차 점검
- 직접 auth 입력 없음 — **시스템별 preset 필수**
- 선택 시스템별 status badge
- `POST /api/suites`

### FR-002: 시스템 카드 (6개)

- manifest `run_form` 동적 렌더
- preset chip + 직접 입력
- 모듈 체크박스 (`selected_module_ids`)
- `POST /api/runs/systems/{code}`

### FR-003: 진행 중 / 최근 Run

`GET /api/runs` 패널 — 실시간 갱신

## 3. 인증 수단 UI

- HOM/MHM: phone, kakao만 실행 가능
- 금융/공동인증서 — placeholder, API 거부

## 4. admin 리다이렉트

admin → `/admin` (execute 접근 시)

## 5. 수용 기준

### AC-001: Suite preset 검증

```gherkin
Given SUITE with hom selected, no hom preset
When submit
Then validation error before API call
```

### AC-002: depends_on

```gherkin
Given contract.list checked, login unchecked
When start run
Then 400 from API
```

## 6. 스크립트

`app/web/static/app.js`
