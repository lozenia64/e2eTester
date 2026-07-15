# CHBOT 시나리오 (챗봇 / 모바일)

이 문서는 `chbot` 시스템의 E2E 테스트 시나리오를 설명한다.

플랫폼 공통 아키텍처(계층 구조, 상태 전이, 이벤트 모델, 아티팩트 전략)는 [E2E_ARCHITECTURE.md](../../E2E_ARCHITECTURE.md)를 참고한다.

## 1. 시스템 개요

- 시스템 코드: `chbot`
- manifest: `app/systems/chbot/manifest.yaml`
- 대상 사이트: `https://chbot.hwgeneralins.com/P29GCdKMTnbsy0PRr` (경로 포함 고정값)
- 플랫폼: 모바일 웹
- **브라우저 기동 순서(필수)**: Playwright로 Chrome을 연 뒤 **모바일 디바이스 모드를 먼저 적용**(`app/systems/access_common/browser.py` 의 `apply_mobile_device_mode()`, executor `build_runtime()` 단계)하고, 그 다음에 사이트에 접속한다.
- 인증 수단: 휴대폰 인증·카카오 인증(`supported_auth_methods: [phone, kakao]`). Run 폼 `auth_method`로 선택한다. 휴대폰 인증은 성명·생년월일·성별코드·통신사·휴대폰 번호를 입력하고 SMS 인증번호는 OTP 패널에서 입력한다. 카카오 인증은 성명·생년월일·성별코드·휴대폰 번호만 필요하며 OTP pause 없이 카카오톡 앱 승인 후 자동 완료한다.
- **전체 순차 점검(SUITE)**: 홈 SUITE 카드의 시스템 체크박스로 포함 여부를 선택할 수 있다. 선택 시 공통 `browser_mode`와 인증 정보로 모듈이 실행된다.
- 실행기: `app/systems/chbot/executor.py` (`ChbotWorkflowExecutor`, `execution_mode = chbot_workflow_step`, `mobile=True`). 메인 접속은 `app/systems/access_common/`을 재사용하고, 간편본인인증·계약조회는 `app/systems/chbot/steps/`에서 처리한다.

## 2. 모듈 목록

`manifest.yaml` `order` 기준:

1. `chbot.main.access` — 메인화면 접속 (`workflow_step: main_access`, `timeout_seconds: 120`)
2. `chbot.simple.auth` — 간편본인인증 (`workflow_step: simple_auth`, `timeout_seconds: 180`)
3. `chbot.contract.list` — 계약조회 (`workflow_step: contract_list`, `timeout_seconds: 120`)

의존성 그래프:

- `chbot.main.access` → 없음
- `chbot.simple.auth` → `chbot.main.access`
- `chbot.contract.list` → `chbot.simple.auth`

## 3. 시나리오 상세

### 3.1 메인화면 접속 (`chbot.main.access`)

1. Playwright로 Chrome(Cursor Playwright MCP와 동일한 영속 프로파일 `%LOCALAPPDATA%/ms-playwright-mcp/mcp-chrome-{workspace_hash}`; `E2E_PLAYWRIGHT_MCP_PROFILE_DIR`로 재정의 가능)을 기동하고 **모바일 디바이스 모드를 먼저 적용**한다.
2. `https://chbot.hwgeneralins.com/P29GCdKMTnbsy0PRr` 으로 직접 이동(`domcontentloaded`)한다.
3. 초기 안내 팝업이 있으면 `닫기` 형태 버튼으로 정리한다(`maybe_close_popup`).
4. 메인화면 스크린샷(`final.png`)을 남기고 "메인화면 접속 성공"으로 종료한다.

### 3.2 간편본인인증 (`chbot.simple.auth`)

메인화면 접속 직후 같은 브라우저 세션에서 챗봇 대화를 이어간다. `auth_method`에 따라 **휴대폰 인증**(§3.2.1) 또는 **카카오 인증**(§3.2.2) 경로로 분기한다. 공통 1~4단계(계약조회 → 본인 정보 확인)는 `app/automation/page_objects/chbot/simple_auth.py` `run_identity_verification()`에서 수행한다.

#### 3.2.1 휴대폰 인증 (`auth_method: phone`)

1. 하단 메시지 입력창(`#message`, placeholder `메세지를 입력하세요.`)에 `계약조회`를 입력하고 전송 버튼(`#btn-chat-send`)을 클릭한다.
2. 챗봇 응답에 `본인 정보 확인` 문구가 표시되는지 확인한다.
3. Run 폼에서 받은 **성명**, **생년월일(6자리 YYMMDD 또는 8자리 YYYYMMDD — 8자리는 앞 2자리를 제거해 6자리로 자동 정규화, `_normalize_birthdate`)**, **성별코드(1~8)** 를 아래 셀렉터로 입력한 뒤 `확인` 버튼을 클릭한다.
   - 성명: `input[name='hnglCtmnm']`
   - 생년월일: `input[name^='ssn1']` (maxlength 6)
   - 성별코드: `select[name^='sex2']` (option value `1`~`8`)
   - 확인: `#btn_conf` (`a[data-sinario='AUT002']`)
4. `간편인증 선택` 문구(실제 제목: `[본인확인]간편인증 선택`)가 표시되는지 확인한다.
5. `휴대폰 인증` 링크(`a:has-text('휴대폰 인증')`)를 클릭한다.
6. `휴대폰 인증` 제목(`h2:has-text('휴대폰 인증')`)이 표시되는지 확인한다.
7. 휴대폰 인증 폼(`.bot_lagacy` 컨테이너)에서 약관 전체동의 체크박스(`input[name='checkbox']`)를 선택하고, Run 폼의 **이름(자동 채움·readonly)**, **통신사**, **휴대폰 번호**를 입력한 뒤 `인증번호` 링크(`a:text-is('인증번호')`)를 클릭해 SMS를 요청한다.
   - 통신사: `select[name='hp_com']` (value `01` SKT, `02` KT, `03` LG U+, `05` SKT알뜰폰, `06` KT알뜰폰, `07` LG U+알뜰폰)
   - 휴대폰 앞자리: `input[name='hndphTlano']` (3자리)
   - 휴대폰 중간: `input[name='hndphTltno']` (4자리)
   - 휴대폰 끝: `input[name='hndphTlsno']` (4자리)
8. Run 을 `WAITING_INPUT` 으로 일시정지한다. 사용자가 웹 대시보드 OTP 패널에 SMS 인증번호를 입력하면 재개한다.
9. 인증번호 입력란(`input[name='smsCertNo']`)에 OTP를 입력하고 하단 `확인` 버튼(`a[data-sinario='AUT003_1']`)을 클릭한다.
10. 챗봇 응답에 `환영합니다` 문구가 표시되면 "간편본인인증 성공"으로 종료한다.

##### 셀렉터 요약 — 휴대폰 인증 (Playwright MCP 수집)

| 단계 | 요소 | CSS 셀렉터 |
|------|------|------------|
| 채팅 | 메시지 입력 | `#message` |
| 채팅 | 전송 | `#btn-chat-send` |
| 본인확인 | 성명 | `input[name='hnglCtmnm']` |
| 본인확인 | 생년월일 | `input[name^='ssn1']` |
| 본인확인 | 성별코드 | `select[name^='sex2']` |
| 본인확인 | 확인 | `#btn_conf`, `a[data-sinario='AUT002']` |
| 간편인증 | 휴대폰 인증 | `a:has-text('휴대폰 인증')` |
| 휴대폰 인증 | 약관 전체동의 | `.bot_lagacy input[name='checkbox']` |
| 휴대폰 인증 | 통신사 | `select[name='hp_com']` |
| 휴대폰 인증 | 휴대폰(앞/중/끝) | `input[name='hndphTlano']`, `hndphTltno`, `hndphTlsno` |
| 휴대폰 인증 | 인증번호 요청 | `a:text-is('인증번호')` |
| 휴대폰 인증 | 인증번호 입력 | `input[name='smsCertNo']` |
| 휴대폰 인증 | 확인 | `a[data-sinario='AUT003_1']` |

#### 3.2.2 카카오 인증 (`auth_method: kakao`)

공통 1~4단계(계약조회 → 본인 정보 확인·확인) 후 카카오 경로를 탄다. OTP pause 없이 한 번에 완료한다(`ChbotSimpleAuthFlow` → `StepCompleted` only). 대기·재시도 상수는 `app/automation/scenarios/rep_homepage/constants.py` (`KAKAO_AUTH_BACKGROUND_WAIT_MS=30000`, `KAKAO_AUTH_MAX_ATTEMPTS=3`)를 사용한다.

1. `간편인증 선택` 문구가 표시되는지 확인한다.
2. `카카오 인증` 링크(`a:has-text('카카오 인증')`)를 클릭한다.
3. `카카오 인증` 제목이 표시되는지 확인한다.
4. 카카오 인증 폼(컨테이너: `xpath=//h2[contains(normalize-space(.),'카카오 인증')]/ancestor::div[contains(@class,'bot_lagacy')][1]`)에서 약관 전체동의(`input[name='checkbox01']`, `label:has-text('약관 전체동의')` 클릭)를 선택한다.
5. **이름**(`input[name='aut_custNm']`)과 **휴대폰 번호**(`input[name='hndphTlano']`, `hndphTltno`, `hndphTlsno`)를 입력한다.
6. 폼 `확인` 버튼(`a.chatting-btn.orange:has-text('확인')`)을 클릭해 카카오 인증을 요청한다.
7. **「카카오 톡으로 인증번호가 발송되었습니다」** 알림 모달의 `확인`을 클릭해 닫는다.
8. 30초 대기 후 사용자가 카카오톡 앱에서 승인했다고 가정하고, 채팅 카드의 **`카카오 인증완료 확인`** 또는 `확인` 버튼(`a:has-text('카카오 인증완료 확인')`, `a.chatting-btn.orange:has-text('확인')`)을 클릭한다.
9. 인증 미완료 안내가 표시되면 6~8단계를 최대 3회 재시도한다.
10. 챗봇 응답에 `환영합니다` 문구가 표시되면 "간편본인인증 성공"으로 종료한다.

##### 셀렉터 요약 — 카카오 인증 (Playwright MCP 수집)

| 단계 | 요소 | CSS 셀렉터 |
|------|------|------------|
| 간편인증 | 카카오 인증 | `a:has-text('카카오 인증')` |
| 카카오 인증 | 컨테이너 | `xpath=//h2[contains(normalize-space(.),'카카오 인증')]/ancestor::div[contains(@class,'bot_lagacy')][1]` |
| 카카오 인증 | 약관 전체동의 | `input[name='checkbox01']`, `label:has-text('약관 전체동의')` |
| 카카오 인증 | 이름 | `input[name='aut_custNm']` |
| 카카오 인증 | 휴대폰(앞/중/끝) | `input[name='hndphTlano']`, `hndphTltno`, `hndphTlsno` |
| 카카오 인증 | 폼 확인(인증 요청) | `a.chatting-btn.orange:has-text('확인')` |
| 카카오 인증 | 발송 알림 확인 | `.d_modal` 내 `span.d_modal_btn.d_modal_ok` (`인증번호가 발송` 문구 모달) |
| 카카오 인증 | 인증완료 확인 | `a:has-text('카카오 인증완료 확인')`, `a.chatting-btn.orange:has-text('확인')` |

### 3.3 계약조회 (`chbot.contract.list`)

간편본인인증 완료(`환영합니다` 응답) 직후 같은 브라우저 세션에서 챗봇이 표시하는 계약 조회 흐름을 이어간다.

1. `계약 조회 기준 선택` 제목(`h2`)이 표시되는지 확인한다.
2. `계약자인 보험` 버튼(`a[data-sinario='INS002'][data-searchkey='01']`)을 클릭한다.
3. `계약 상태 선택` 제목이 표시되는지 확인한다.
4. `정상` 버튼(`a[data-sinario='INS003'][data-searchkey='00']`)을 클릭한다.
5. `계약목록` 문구와 `(총 N건)` 형태의 총 건수(예: `총 1건`)가 표시되는지 확인하고 "계약조회 성공 (총 N건)"으로 종료한다.

#### 셀렉터 요약 (Playwright MCP 수집)

| 단계 | 요소 | CSS 셀렉터 |
|------|------|------------|
| 기준 선택 | 제목 | `h2:has-text('계약 조회 기준 선택')` |
| 기준 선택 | 계약자인 보험 | `a[data-sinario='INS002'][data-searchkey='01']` |
| 상태 선택 | 제목 | `h2:has-text('계약 상태 선택')` |
| 상태 선택 | 정상 | `a[data-sinario='INS003'][data-searchkey='00']` |
| 목록 | 계약목록·총 건수 | `계약목록` 텍스트, 본문 정규식 `총\s*\d+\s*건` |

## 4. 향후 시나리오

계약 상세 조회 등 추가 업무는 추후 모듈로 하나씩 추가한다. 모듈을 추가할 때는 이 문서와 `app/systems/chbot/manifest.yaml`을 함께 갱신한다.
