# HRP 시나리오 (현장출동 홈페이지 / PC)

이 문서는 `hrp` 시스템의 E2E 테스트 시나리오를 설명한다.

플랫폼 공통 아키텍처(계층 구조, 상태 전이, 이벤트 모델, 아티팩트 전략)는 [E2E_ARCHITECTURE.md](../../E2E_ARCHITECTURE.md)를 참고한다.

## 1. 시스템 개요

- 시스템 코드: `hrp`
- manifest: `app/systems/hrp/manifest.yaml`
- 대상 사이트: `https://www.eagleprm.co.kr`
- 플랫폼: PC 웹
- 인증 수단: 휴대폰 인증 단일(`supported_auth_methods: [phone]`). 웹 대시보드 Run 폼에서 아이디·비밀번호를 입력하고, SMS 인증번호는 Run 화면 OTP 패널에서 입력한다.
- **전체 순차 점검(SUITE)**: 홈 SUITE 카드의 시스템 체크박스로 포함 여부를 선택할 수 있다. 선택 시 공통 `browser_mode`와 인증 정보로 모듈이 실행된다.
- 실행기: `app/systems/hrp/executor.py` (`HrpWorkflowExecutor`, `execution_mode = hrp_workflow_step`). 메인 접속은 `app/systems/access_common/`을 재사용하고, 로그인은 `app/systems/hrp/steps/`에서 처리한다.

## 2. 모듈 목록

`manifest.yaml` `order` 기준:

1. `hrp.main.access` — 메인화면 접속 (`workflow_step: main_access`, `timeout_seconds: 120`)
2. `hrp.login` — 로그인 (`workflow_step: login`, `timeout_seconds: 180`)
3. `hrp.salvage.bid.inquiry.list` — 잔존물 입찰 조회(목록) (`workflow_step: salvage_bid_inquiry_list`, `timeout_seconds: 180`)
4. `hrp.salvage.bid.inquiry.detail` — 잔존물 입찰 조회(상세) (`workflow_step: salvage_bid_inquiry_detail`, `timeout_seconds: 180`)

의존성 그래프:

- `hrp.main.access` → 없음
- `hrp.login` → `hrp.main.access`
- `hrp.salvage.bid.inquiry.list` → `hrp.login`
- `hrp.salvage.bid.inquiry.detail` → `hrp.salvage.bid.inquiry.list`

## 3. 시나리오 상세

### 3.1 메인화면 접속 (`hrp.main.access`)

1. Playwright로 Chrome(영속 프로파일 `~/.e2etester/hrp-chrome-profile`)을 기동한다.
2. `https://www.eagleprm.co.kr` 으로 직접 이동(`domcontentloaded`)한다. 사이트 정책상 로그인 화면(`/first.do`)으로 리다이렉트될 수 있다.
3. 초기 안내 팝업이 있으면 `닫기` 형태 버튼으로 정리한다(`app/systems/access_common/browser.py` 의 `maybe_close_popup`).
4. 메인화면 스크린샷(`final.png`)을 남기고 "메인화면 접속 성공"으로 종료한다.

### 3.2 로그인 (`hrp.login`)

1. 로그인 화면(`/first.do`)이 아니면 해당 URL로 이동한다.
2. 초기 팝업이 있으면 정리한다.
3. Run 폼에서 받은 아이디·비밀번호를 아래 셀렉터로 입력한다.
   - 아이디: `#firstId` (placeholder `아이디`, 7자 이상)
   - 비밀번호: `#firstPw` (placeholder `비밀번호`)
4. `로그인` 버튼(`#btnRA`, class `login-btn`)을 클릭한다. 사이트는 `HrpA001Ctr` AJAX 로그인 후 성공 시 사용자 인증 팝업을 연다.
5. **사용자 인증 팝업**(cubePopup iframe, `beforeUrlMaster/A/hrpA080.do`)에서 `인증번호 받기` 버튼(`#btnSMS`)을 클릭해 SMS 인증번호를 요청한다. 발송 성공 시 `#setTime` 타이머(3분)가 시작된다.
6. Run 을 `WAITING_INPUT` 으로 일시정지한다. 사용자가 웹 대시보드 OTP 패널에 4~8자리 인증번호를 입력하면 재개한다.
7. iframe 내 `#smsNum` 에 인증번호를 입력하고 `확인` 버튼(`#btnOk`)을 클릭한다.
8. URL이 `/amain.do` 이면 "로그인 성공"으로 종료한다. 실패 시 브라우저 알림 메시지를 오류로 보고한다.

#### 셀렉터 요약 (Playwright MCP 수집)

| 단계 | 요소 | CSS 셀렉터 |
|------|------|------------|
| 로그인 | 아이디 | `#firstId` |
| 로그인 | 비밀번호 | `#firstPw` |
| 로그인 | 로그인 | `#btnRA` |
| 팝업 | iframe | `[id^="__POP_ID_"] iframe` |
| 팝업 | 제목 | `h1.popup-title` (텍스트 `사용자 인증`) |
| 팝업 | 닫기 | `button.popup-close` |
| SMS 인증 | 휴대폰 표시 | `#hpNo` |
| SMS 인증 | 타이머 | `#setTime` |
| SMS 인증 | 인증번호 입력 | `#smsNum` (`maxlength="8"`, digit) |
| SMS 인증 | 인증번호 받기 | `#btnSMS` |
| SMS 인증 | 확인 | `#btnOk` |
| SMS 인증 | 취소 | `#btnCancel` |

### 3.3 잔존물 입찰 조회(목록) (`hrp.salvage.bid.inquiry.list`)

1. 로그인 완료 후 메인화면(`/amain.do`)에서 시작한다. 다른 URL이면 `/amain.do`로 이동한다.
2. 상단 메뉴 **잔존물** → **잔존물입찰조회**를 클릭한다.
3. **목록 검증**: 페이지 제목 `잔존물입찰조회`(h2), 하단 탭 **잔존물입찰조회** 생성, iframe `workArea_hrpF020` 내 **총 N건** 건수 표시, 목록 **순번 1** 행·접수번호 존재를 확인하면 성공한다.

### 3.4 잔존물 입찰 조회(상세) (`hrp.salvage.bid.inquiry.detail`)

1. 목록 모듈 직후 **잔존물입찰조회** 화면(동일 브라우저 세션)에서 시작한다.
2. 순번 1 행의 **접수번호** 셀을 클릭해 상세 화면으로 진입한다.
3. **상세 검증**: 페이지 제목 `잔존물입찰`(h2), 하단 탭 **잔존물입찰** 생성, iframe `workArea_hrpF021` 내 **등록자 정보·등록정보·사고정보·차량정보** 섹션(h3) 존재를 확인하면 성공한다.

#### 셀렉터 요약 (Playwright MCP 수집)

| 단계 | 요소 | Playwright / CSS |
|------|------|------------------|
| 메뉴 | 잔존물 | `get_by_role('link', name='잔존물')` |
| 메뉴 | 잔존물입찰조회 | `get_by_role('link', name='잔존물입찰조회')` |
| 목록 | 페이지 제목 | `get_by_role('heading', name='잔존물입찰조회', level=2)` |
| 목록 | work iframe | `iframe[name="workArea_hrpF020"]` |
| 목록 | 총 건수 | `get_by_text(/총\s*\d+\s*건/)` (iframe 내) |
| 목록 | 순번 1 / 접수번호 | `get_by_role('row').filter(has_text=접수번호패턴)` 후 첫 `cell`·접수번호 `cell` |
| 상세 | 페이지 제목 | `get_by_role('heading', name='잔존물입찰', level=2)` |
| 상세 | work iframe | `iframe[name="workArea_hrpF021"]` |
| 상세 | 정보 섹션 | `get_by_role('heading', name='등록자 정보'|'등록정보'|'사고정보'|'차량정보', level=3)` |

## 4. UI 입력 모델

홈 화면의 `HRP` 실행 카드에는 아래 입력이 있다.

- 브라우저 실행 모드 (`headed` / `headless`, 기본값 `headed`)
- 아이디 (현장출동 홈페이지 로그인 ID, 7자 이상)
- 비밀번호 (`password` 타입)

추가 규칙:

- 브라우저 실행 모드 help_text: `headed` 를 선택하면 웹에서 실행할 때 로컬 PC에 실제 브라우저 창이 추가로 열린다.
- SMS 인증번호는 Run 폼이 아니라 Run 화면 OTP 패널에서 제출한다.

## 5. 향후 시나리오

현장출동 본 업무 시나리오는 추후 모듈로 하나씩 추가한다. 모듈을 추가할 때는 이 문서와 `app/systems/hrp/manifest.yaml`을 함께 갱신한다.
