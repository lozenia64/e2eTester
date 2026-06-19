# HWTC Playwright MCP 탐색

## MCP 서버 실행

```bash
npx -y @playwright/mcp@latest --port 8931 --browser chrome
```

프로젝트 `.cursor/mcp.json` 이 `http://localhost:8931/mcp` 를 가리킵니다.  
Cursor에서 MCP 도구를 쓰려면 **새 채팅**을 열고 Playwright MCP가 연결됐는지 확인하세요.

## 로그인 페이지

| 요소 | CSS 셀렉터 | 비고 |
|------|------------|------|
| 아이디 | `#userId` | `input[name="userId"]` |
| 비밀번호 | `#password` | `input[name="password"]` |
| 로그인 | `button.btn.org.login` | 텍스트 `LOGIN`, `onclick="fn_submit()"` |
| 팝업 컨테이너 | `#popAlert` | `class="popup type3"` |
| 팝업 닫기 | `#popAlert button.btn-close` | `onclick="fn.popupClose()"` |
| 팝업 확인 | `#popAlert button.btn.fill.small.org.ok` | `onclick="fn.popupCloseId('#popAlert')"` |

스냅샷: `research/hwtc/login_snapshot.md`

## 30일 이상 미로그인 팝업 (로그인 직후, 있을 수 있음)

- 제목: `30일이상 미 로그인 하여, 본인인증을 진행합니다.`
- 확인 클릭 시 `/login/loginSmsForm.do` 로 이동
- 확인 버튼은 뷰포트 밖에 그려져 일반 click 이 실패할 수 있음 → `#popAlert button.btn.fill.small.org.ok` JS click 사용

## SMS 인증 화면 (`/login/loginSmsForm.do`)

| 요소 | CSS 셀렉터 | 비고 |
|------|------------|------|
| 인증번호 입력 | `#certiKey` | `input[name="certiKey"]`, maxlength 5, 발급 전 disabled |
| 발급 | `#sendBtn1` | `onclick="sendCertiKey()"`, 텍스트 `발급` |
| 재발급 | `#sendBtn2` | 발급 후 표시, 텍스트 `재발급` |
| 확인(제출) | `#sendBtn3` | `onclick="fn_submit()"`, 발급 후 표시 |
| 발급 안내 팝업 | `#popAlert h2` | `인증번호를 입력하세요.` |

## 자동화 구현

- 시나리오 문서: `docs/scenarios/hwtc.md`
- 스텝 모듈: `app/systems/hwtc/steps/phone_auth.py`
- OTP 일시정지: `HwtcWorkflowExecutor` 가 `WAITING_INPUT` 반환 → 웹 Run OTP 패널

## 프로브 스크립트

```bash
HWTC_USER_ID='your-id' HWTC_PASSWORD='your-pw' python3 research/hwtc/mcp_probe.py
```

수동 로그인 후 스냅샷 수집:

```bash
HWTC_MANUAL_LOGIN=1 python3 research/hwtc/mcp_probe.py
```
