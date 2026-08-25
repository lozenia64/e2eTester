# SPEC-UI-002: 점검 실행 페이지

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-UI-002` |
| **상태** | `approved` (시각·레이아웃은 `2026-08-24-execute-promotion-design.md` §4.3 이 우선) |
| **의존** | `SPEC-RUN-001`, `SPEC-SUITE-001`, `SPEC-PRESET-001` |

## 1. 페이지

`GET /runs/execute` → `execute.html`

## 2. 구성

### FR-001: SUITE 실행 조건 패널

- 전체 시스템 순차 점검
- 직접 auth 입력 없음 — **시스템별 preset 필수**
- 선택 시스템별 status badge
- `POST /api/suites`

### FR-002: 시스템 실행 조건 패널

- manifest `run_form` 동적 렌더
- preset chip + 직접 입력
- 모듈 체크박스 (`selected_module_ids`)
- `POST /api/runs/systems/{code}`

### FR-003: 진행 중 / 최근 Run

`GET /api/runs` 패널 — 실시간 갱신

### FR-004: 마스터-디테일 레이아웃

- 좌측: 점검 대상 선택 목록(SUITE + 허용 시스템). 각 항목에 오늘 상태 배지
- 우측: 선택 대상의 실행 조건 패널. 모듈 의존성 그래프가 상단 지배 요소
- 기본 선택은 SUITE
- `< 1024px` 에서 1열로 붕괴하고 좌측 목록은 가로 스크롤 칩 행이 된다

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

### AC-003: 넌스크롤 마스터-디테일

- **Given** 허용 시스템이 1~6개인 `operator`
- **When** `GET /runs/execute` 를 1366 · 1920 · 2560 px 에서 연다
- **Then** `body` 세로 스크롤이 0이고, 실행 버튼이 스크롤 없이 보이며,
  내부 스크롤을 갖는 영역은 우측 조건 열 하나뿐이다
- **And** 좌측 항목을 선택하면 해당 패널만 보이고 나머지는 감춰진다

## 6. 스크립트

`app/web/static/app.js`
