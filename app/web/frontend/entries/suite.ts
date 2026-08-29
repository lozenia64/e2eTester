// 수트 상세 화면 엔트리. 배선만 한다 — 로직은 suite/ 아래 모듈에 있다.
// 최초 렌더는 서버 마크업이 끝낸다. 이후 갱신은 bindSuiteSocket 이 여는
// 수트 WS + 하위 Run 진행 WS 의 이벤트마다 이뤄진다(설계 §3.3).
import "../suite/styles.css";
import { bindSuiteActions, bindSuiteOtpForm } from "../suite/actions";
import { bindSuiteSocket } from "../suite/socket";

document.addEventListener("DOMContentLoaded", () => {
  bindSuiteActions();
  bindSuiteOtpForm();
  bindSuiteSocket();
});
