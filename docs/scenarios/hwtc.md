# HWTC 시나리오 (연수원 / PC)

이 문서는 `hwtc` 시스템의 E2E 테스트 시나리오를 설명한다.

플랫폼 공통 아키텍처(계층 구조, 상태 전이, 이벤트 모델, 아티팩트 전략)는 [E2E_ARCHITECTURE.md](../../E2E_ARCHITECTURE.md)를 참고한다.

## 1. 시스템 개요

- 시스템 코드: `hwtc`
- manifest: `app/systems/hwtc/manifest.yaml`
- 대상 사이트: `https://sls.hwgeneralins.com`
- 플랫폼: PC 웹
- 인증 수단: 휴대폰 인증 단일(`supported_auth_methods: [phone]`). 웹 대시보드 Run 폼에서 아이디·비밀번호를 입력하고, SMS 인증번호는 Run 화면 OTP 패널에서 입력한다(한화스마트포털 HSP와 동일 ID/PW).
- **전체 순차 점검(SUITE)**: 홈 SUITE 카드의 시스템 체크박스로 포함 여부를 선택할 수 있다. 선택 시 공통 `browser_mode`와 인증 정보로 모듈이 실행된다.
- 실행기: `app/systems/hwtc/executor.py` (`HwtcWorkflowExecutor`, `execution_mode = hwtc_workflow_step`). 메인 접속은 `app/systems/access_common/`을 재사용하고, 휴대폰 인증·동영상 재생은 `app/systems/hwtc/steps/`에서 처리한다.

## 2. 모듈 목록

`manifest.yaml` `order` 기준:

1. `hwtc.main.access` — 메인화면 접속 (`workflow_step: main_access`, `timeout_seconds: 120`)
2. `hwtc.phone.auth` — 휴대폰 인증 (`workflow_step: phone_auth`, `timeout_seconds: 180`)
3. `hwtc.video.playback` — 동영상 재생 (`workflow_step: video_playback`, `timeout_seconds: 180`)

의존성 그래프:

- `hwtc.main.access` → 없음
- `hwtc.phone.auth` → `hwtc.main.access`
- `hwtc.video.playback` → `hwtc.phone.auth`

## 3. 시나리오 상세

### 3.1 메인화면 접속 (`hwtc.main.access`)

1. Playwright로 Chrome(Cursor Playwright MCP와 동일한 영속 프로파일 `%LOCALAPPDATA%/ms-playwright-mcp/mcp-chrome-{workspace_hash}`; `E2E_PLAYWRIGHT_MCP_PROFILE_DIR`로 재정의 가능)을 기동한다.
2. `https://sls.hwgeneralins.com` 으로 직접 이동(`domcontentloaded`)한다. 사이트 정책상 로그인 화면(`/login/loginForm.do`)으로 리다이렉트될 수 있다.
3. 초기 안내 팝업이 있으면 `닫기` 형태 버튼으로 정리한다(`app/systems/access_common/browser.py` 의 `maybe_close_popup`).
4. 메인화면 스크린샷(`final.png`)을 남기고 "메인화면 접속 성공"으로 종료한다.

### 3.2 휴대폰 인증 (`hwtc.phone.auth`)

1. 로그인 화면(`/login/loginForm.do`)이 아니면 해당 URL로 이동한다.
2. 초기 팝업이 있으면 정리한다.
3. Run 폼에서 받은 아이디·비밀번호를 아래 셀렉터로 입력한다.
   - 아이디: `#userId` (`input[name="userId"]`, placeholder `아이디를 입력해주세요.`)
   - 비밀번호: `#password` (`input[name="password"]`, placeholder `비밀번호를 입력해주세요.`)
4. `LOGIN` 버튼(`button.btn.org.login`, `onclick="fn_submit()"`)을 클릭한다. 사이트는 `/login/ajax/login.do`로 AJAX 로그인 후 성공 시 후속 화면으로 진행한다.
5. **30일 이상 미로그인 팝업**(있을 수 있음): `#popAlert` 모달의 제목 `30일이상 미 로그인 하여, 본인인증을 진행합니다.` 가 보이면 `#popAlert button.btn.fill.small.org.ok`(확인) 또는 `button.btn-close`(닫기)로 닫는다. 확인 시 `/login/loginSmsForm.do` 로 이동한다.
6. 휴대폰 인증 화면(`/login/loginSmsForm.do`)에서 `발급` 버튼(`#sendBtn1`, `onclick="sendCertiKey()"`)을 클릭해 SMS 인증번호를 요청한다.
7. 안내 팝업 `인증번호를 입력하세요.` 가 뜨면 `#popAlert` 의 `확인` 버튼으로 닫는다. 인증번호 입력란(`#certiKey`)이 활성화되고 제출 버튼(`#sendBtn3`)이 표시된다.
8. Run 을 `WAITING_INPUT` 으로 일시정지한다. 사용자가 웹 대시보드 OTP 패널에 5자리 인증번호를 입력하면 재개한다.
9. `#certiKey` 에 인증번호를 입력하고 `확인` 버튼(`#sendBtn3`, `onclick="fn_submit()"`)을 클릭한다.
10. URL이 `/main/main.do` 이면 "휴대폰 인증 성공"으로 종료한다. 실패 시 브라우저 알림 메시지를 오류로 보고한다.

#### 셀렉터 요약 (Playwright MCP 수집)

| 단계 | 요소 | CSS 셀렉터 |
|------|------|------------|
| 로그인 | 아이디 | `#userId` |
| 로그인 | 비밀번호 | `#password` |
| 로그인 | LOGIN | `button.btn.org.login` |
| 장기 미로그인 팝업 | 컨테이너 | `#popAlert` |
| 장기 미로그인 팝업 | 확인 | `#popAlert button.btn.fill.small.org.ok` |
| 장기 미로그인 팝업 | 닫기 | `#popAlert button.btn-close` |
| SMS 인증 | 인증번호 입력 | `#certiKey` (`input[name="certiKey"]`, maxlength 5) |
| SMS 인증 | 발급 | `#sendBtn1` |
| SMS 인증 | 재발급 | `#sendBtn2` (발급 후 표시) |
| SMS 인증 | 확인(제출) | `#sendBtn3` |
| SMS 안내 팝업 | 확인 | `#popAlert button.btn.fill.small.org.ok` |

### 3.3 동영상 재생 (`hwtc.video.playback`)

1. 메인화면(`/main/main.do`)이 아니면 해당 URL로 이동한다.
2. 상단 메뉴 `콘텐츠플러스`에 마우스를 올린 뒤 `IT교육과정` 링크(`/ctnt/2000000047/plusL.do`)를 클릭한다.
3. `교육영상` 목록에서 첫 번째 항목의 `.cover.vod a[onclick^="goView"]` 를 통해 상세화면(`/ctnt/plusF.do`)으로 이동한다. (썸네일 `.thumb` 클릭만으로는 상세 진입이 안 되는 경우가 있어 `goView` 호출을 사용한다.)
4. Video.js 재생 컨트롤을 JS click 으로 누른다. 우선 `.vjs-big-play-button`(접근성 이름 `Play Video`), 없으면 `.video-js .vjs-poster` 를 사용한다. 일반 Playwright `click()` 은 뷰포트/레이어 이슈로 실패할 수 있으며, 재생 시작 후에는 big-play 버튼이 숨겨져 `is_visible()` 이 false 가 된다.
5. **주의**: 재생이 시작된 뒤 `.video-js` 영역을 추가 클릭하면 일시정지되므로 하지 않는다.
6. 30초 동안 2초 간격으로 재생 신호를 샘플링한다.
7. 재생 성공 판정(하나라도 만족하면 통과):
   - `region "Video Player"` 안의 **Pause / 일시정지** 버튼이 보임
   - **Remaining Time** 텍스트(`-6:29` 형식)가 5초 이상 카운트다운
   - (보조) `.video-js.vjs-playing`, `video.currentTime` 증가
8. 플레이어 상태는 `page.evaluate(document.querySelector…)` 에 의존하지 않고, **Playwright role/locator**(`region "Video Player"`, `button "Pause"`, 남은 시간 텍스트)를 우선한다. JS `evaluate` 는 보조 신호만 읽는다.
9. 재생 시작 직후 8초 프로브에서 확인되지 않아도 즉시 실패하지 않고, 30초 관찰 단계에서 다시 판정한다.

#### 셀렉터 요약 (Playwright MCP 수집)

| 단계 | 요소 | 셀렉터 |
|------|------|--------|
| 메인 | IT교육과정 메뉴 | `link "IT교육과정"` (`/ctnt/2000000047/plusL.do`) |
| 목록 | 첫 번째 교육영상 | `h3:has-text("교육영상")` 하위 `ul li` 첫 항목 `.thumb` |
| 목록 | 상세 진입 JS | `.cover.vod a[onclick^="goView"]` (썸네일 클릭과 동일) |
| 상세 | 플레이어 영역 | `region "Video Player"` |
| 상세 | 재생 중 확인 | `button "Pause"` 또는 남은 시간 `-M:SS` 텍스트 카운트다운 |
| 상세 | 동영상 요소 | `video` (보조) |
| 상세 | 포스터(썸네일) | `.video-js .vjs-poster` |
| 상세 | 재생 버튼 | `.vjs-big-play-button` |

## 4. 향후 시나리오

연수원 본 업무 시나리오는 추후 모듈로 하나씩 추가한다. 모듈을 추가할 때는 이 문서와 `app/systems/hwtc/manifest.yaml`을 함께 갱신한다.
