# FP 시나리오 (영업가족 위촉서류 등록 / PC)

이 문서는 `fp` 시스템의 E2E 테스트 시나리오를 설명한다.

플랫폼 공통 아키텍처(계층 구조, 상태 전이, 이벤트 모델, 아티팩트 전략)는 [E2E_ARCHITECTURE.md](../../E2E_ARCHITECTURE.md)를 참고한다.

## 1. 시스템 개요

- 시스템 코드: `fp`
- manifest: `app/systems/fp/manifest.yaml`
- 대상 사이트: `https://fp.hwgeneralins.com`
- 플랫폼: PC 웹
- 인증 수단: 휴대폰 인증 단일(`supported_auth_methods: [phone]`). Run 폼에서 이름·주민등록번호·통신사·휴대폰번호를 입력하고, SMS 인증번호는 Run 화면 OTP 패널에서 입력한다.
- **전체 순차 점검(SUITE)**: 홈 SUITE 카드의 시스템 체크박스로 포함 여부를 선택할 수 있다. 선택 시 공통 `browser_mode`와 인증 정보로 모듈이 실행된다.
- 실행기: `app/systems/fp/executor.py` (`FpWorkflowExecutor`, `execution_mode = fp_workflow_step`). 메인 접속은 `app/systems/access_common/`을 재사용하고, 본인인증은 `app/systems/fp/steps/identity_verification.py`, 서류작성은 `app/systems/fp/steps/document_writing.py`에서 처리한다.

## 2. 모듈 목록

`manifest.yaml` `order` 기준:

1. `fp.main.access` — 메인화면 접속 (`workflow_step: main_access`, `timeout_seconds: 120`)
2. `fp.identity.verification` — FP 본인인증 (`workflow_step: identity_verification`, `timeout_seconds: 300`)
3. `fp.document.writing` — FP 서류작성 (`workflow_step: document_writing`, `timeout_seconds: 420`)

의존성 그래프:

- `fp.main.access` → 없음
- `fp.identity.verification` → `fp.main.access`
- `fp.document.writing` → `fp.identity.verification`

## 3. 시나리오 상세

### 3.1 메인화면 접속 (`fp.main.access`)

1. Playwright로 Chrome(영속 프로파일 `~/.e2etester/fp-chrome-profile`)을 기동한다.
2. `https://fp.hwgeneralins.com` 으로 직접 이동(`domcontentloaded`)한다.
3. 초기 안내 팝업이 있으면 `닫기` 형태 버튼으로 정리한다(`app/systems/access_common/browser.py` 의 `maybe_close_popup`).
4. 메인화면 스크린샷(`final.png`)을 남기고 "메인화면 접속 성공"으로 종료한다.

### 3.2 FP 본인인증 (`fp.identity.verification`)

메인화면 접속 직후 동일 브라우저 세션에서 진행한다.

1. **영업가족계약서 작성** 링크(`a[href="/fp/loan/sales01.do"]`)를 클릭해 `/fp/loan/sales01.do` 본인확인 화면으로 이동한다. 이미 해당 URL이면 생략한다.
2. `개인정보처리동의` 제목(`h3`)이 표시되는지 확인한다.
3. 개인정보처리동의 우측 **전체동의** 체크박스(`#agreeAll`)를 선택한다. `<span>`이 체크박스를 가리므로 `label:has(#agreeAll)` 클릭을 사용한다.
4. Run 폼에서 받은 **이름**(`#name`), **주민등록번호 앞자리**(`#ssn1`), **뒷자리**(`#ssn2`)를 입력한다. 앞자리는 `#ssn1`에 `fill` 한다. 뒷자리는 `#ssn2` 포커스로 nfilter 키패드를 연 뒤, 섞인 키패드 이미지를 `num_no_secretmerged`·`num_no_secretmap` 기준으로 픽셀 비교(Hungarian 최적 배정)해 숫자→`areaId` 매핑을 만든 다음 `nFilterClick(areaId)` 로 입력한다. 7자리 전체 입력 후 `decode-ssn-register.json` 으로 보이는 앞자리가 기대값과 다르면 해당 숫자 `areaId` 를 후보 전체에서 교체 시도한다(단일 키 클릭 decode 는 500 이므로 사용하지 않음). 입력 후 `#nfilter_num_content #nfilter_enter_num` 으로 키패드를 닫고 `nFilterSecElement` 길이(7자리×10)와 `#ssn2_nfilter_sec` 암호화 값을 확인한다.
5. 본인확인수단 **휴대폰** 라디오(`#name_cert02`, `label:has(#name_cert02)`)를 선택한다. `휴대폰인증` 섹션이 표시되면 성공이다.
6. Run 폼의 **통신사**·**휴대폰번호**를 아래 필드에 입력한 뒤 **인증번호요청**(`#btnSendAuth`)을 클릭한다. 클릭 시 사이트 JS가 순서대로 `POST /cmcom/decode-ssn-register.json`(nfilter 암호화 주민번호 등록) → `POST /cmcom/hp-sms-request.json`(SMS 발송) 을 호출한다. AJAX 오류 시 브라우저 알림은 `데이터 전송이 지연되고 있습니다` 로 통일되어 표시된다(`biz-common.js` 공통 오류 처리).
   - 통신사: `#hpCom` (`01` SKT, `02` KT, `03` LGT, `05`~`07` 알뜰폰)
   - 번호 앞자리: `#hndphTlano` (select, `010`/`011`)
   - 국번·뒷자리: `#hndphTltno`, `#hndphTlsno`
7. Run 을 `WAITING_INPUT` 으로 일시정지한다. 사용자가 웹 대시보드 OTP 패널에 4~8자리 인증번호를 입력하면 재개한다.
8. `#smsCertNo` 에 인증번호를 입력하고 **인증확인** 버튼(`#btnSmsConfirm`)을 클릭한다.
9. 하단 **계약서 체결하기** 버튼(`#submitBtn`)을 클릭한다.
10. `https://fp.hwgeneralins.com/fp/loan/sales02.do` 로 이동하면 "FP 본인인증 성공"으로 종료한다. 실패 시 브라우저 알림 메시지를 오류로 보고한다.

#### 셀렉터 요약 (Playwright MCP 수집)

| 단계 | 요소 | CSS 셀렉터 |
|------|------|------------|
| 진입 | 영업가족계약서 작성 | `a[href="/fp/loan/sales01.do"]` |
| 동의 | 개인정보처리동의 제목 | `h3` (텍스트 `개인정보처리동의`) |
| 동의 | 전체동의 | `#agreeAll` / `label:has(#agreeAll)` |
| 본인확인 | 이름 | `#name` |
| 본인확인 | 주민등록번호 앞자리 | `#ssn1` |
| 본인확인 | 주민등록번호 뒷자리 | `#ssn2` + scrambled keypad `nFilterClick(areaId)` |
| 본인확인 | 휴대폰 | `#name_cert02` / `label:has(#name_cert02)` |
| 휴대폰인증 | 통신사 | `#hpCom` |
| 휴대폰인증 | 번호 앞자리 | `#hndphTlano` |
| 휴대폰인증 | 번호 국번 | `#hndphTltno` |
| 휴대폰인증 | 번호 뒷자리 | `#hndphTlsno` |
| 휴대폰인증 | 인증번호요청 | `#btnSendAuth` |
| 휴대폰인증 | 인증번호 입력 | `#smsCertNo` |
| 휴대폰인증 | 인증확인 | `#btnSmsConfirm` |
| 완료 | 계약서 체결하기 | `#submitBtn` |
| 완료 | 계약서 작성 화면 | `/fp/loan/sales02.do` |

### 3.3 FP 서류작성 (`fp.document.writing`)

본인인증 직후 동일 브라우저 세션에서 `/fp/loan/sales02.do` 계약서 작성 화면으로 이어진다.

1. **계약서 작성** 화면(`https://fp.hwgeneralins.com/fp/loan/sales02.do`)에서 시작한다. URL이 다르면 해당 경로로 이동한다.
2. 순번 **8** `(신)정보보호서약서_설계사대리점` 행의 **양식보기** 버튼(`#btnGroup8`)을 클릭한다.
3. **10초** 대기한다(OZ 양식 탭 로드 안정화).
4. 새 탭(`https://ozhome.hwgeneralins.com/ozwebroot/sales02_oz.jsp`)에서 OZ 뷰어가 로드되는지 확인한다. 양식 본문은 DOM 텍스트가 아니라 canvas(문서 2번째·서명란 3번째)로 렌더링되므로, 제출하기 버튼과 canvas 크기로 준비 여부를 판단한다.
5. 양식 우측 하단 **서명란 overlay canvas**(index 2, 약 124×43px)를 `scrollIntoViewIfNeeded` 로 화면에 올린 뒤, `focus` + **trusted mouse** 로 **O** 형태 원을 그린다. `INPUT_CHECK_VALIDITY` 가 `valid` 이고 `INPUT_JSON.sign` 이 채워져야 한다. (문서 canvas 에 synthetic mouse 이벤트를내면 픽셀만 찍히고 OZ 가 서명으로 인식하지 않으며, 스크롤 없이 그리면 서명란이 화면 밖이라 실패한다.) 이후 팝업 하단 **제출하기**(`#btnSaveCert`)를 클릭한다.
6. **10초** 대기한다(양식 저장 반영).
7. 순번 8 행 상태 셀(`#check8`)에 **작성완료**가 표시되는지 확인한다.
8. 하단 **인증하기** 버튼(`#btnSaveCert`)을 클릭한다. 미제출 양식이 남아 있으면 `저장되지 않은 양식이 …건 있습니다` 확인(confirm)이 뜰 수 있으며, 자동 수락한다.
9. **휴대폰인증** 영역(`#phoneCert`)이 표시되면 **인증번호요청**(`#btnSendAuth`)을 클릭한다. `POST /cmcom/hp-sms-request.json`(파라미터 `authFlgcd: "2"`) 응답을 확인한다.
10. Run 을 `WAITING_INPUT` 으로 일시정지한다. 사용자가 웹 대시보드 OTP 패널에 4~8자리 인증번호를 입력하면 재개한다.
11. `#smsCertNo` 에 인증번호를 입력하고 하단 **제출하기** 버튼(`#btnSave`)을 클릭한다.
12. `https://fp.hwgeneralins.com/fp/loan/sales03.do` 로 이동하면 "FP 서류작성 성공"으로 종료한다.

#### 셀렉터 요약 (Playwright MCP 수집)

| 단계 | 요소 | CSS 셀렉터 |
|------|------|------------|
| 양식 | 순번 8 양식보기 | `#btnGroup8` |
| 양식 | 순번 8 작성 상태 | `#check8` (텍스트 `작성완료`) |
| OZ 팝업 | 제출하기 | `#btnSaveCert` (팝업 페이지) |
| OZ 팝업 | 서명란 (그리기 대상) | `canvas` 3번째 (index 2) — scroll + trusted mouse |
| OZ 팝업 | 서명 등록 확인 | `OZViewer.GetInformation('INPUT_CHECK_VALIDITY')` = `valid` |
| 인증 | 인증하기 | `#btnSaveCert` (메인 페이지) |
| 인증 | 휴대폰인증 영역 | `#phoneCert` |
| 인증 | 인증번호요청 | `#btnSendAuth` |
| 인증 | 인증번호 입력 | `#smsCertNo` |
| 완료 | 제출하기 | `#btnSave` |
| 완료 | 작성완료 화면 | `/fp/loan/sales03.do` |

## 4. UI 입력 모델

홈 화면의 `FP` 실행 카드에는 아래 입력이 있다.

- 브라우저 실행 모드 (`headed` / `headless`, 기본값 `headed`)
- 이름
- 주민등록번호 앞자리 (6자리, `YYMMDD`)
- 주민등록번호 뒷자리 (`password` 타입, 7자리)
- 통신사 (SKT·KT·LGU+·SKT/KT/LGU+ 알뜰폰)
- 휴대폰 번호 (010 또는 011로 시작하는 11자리 숫자)

추가 규칙:

- 주민등록번호 뒷자리 필드는 `password` 타입으로 마스킹되며, help_text 로 「주민등록번호 뒷 7자리」를 안내한다.
- 브라우저 실행 모드 help_text: `headed` 를 선택하면 웹에서 실행할 때 로컬 PC에 실제 브라우저 창이 추가로 열린다.
- SMS 인증번호는 Run 폼이 아니라 Run 화면 OTP 패널에서 제출한다.

## 5. 향후 시나리오

계약서 작성 본 업무 시나리오 중 나머지 양식·단계는 추후 모듈로 하나씩 추가한다. 모듈을 추가할 때는 이 문서와 `app/systems/fp/manifest.yaml`을 함께 갱신한다.
