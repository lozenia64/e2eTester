// 런 상세 화면 엔트리. 배선만 한다 — 로직은 run/ 아래 모듈에 있다.
// 최초 렌더는 서버 마크업이 끝내고, 이후 상태는 소켓 이벤트마다 다시 계산한다.
import "../run/styles.css";
import { bindOtpForm, bindRunActions } from "../run/actions";
import { applyFocus } from "../run/modules";
import { bindRunSocket, renderProgress, startRuntimeTicker } from "../run/socket";

document.addEventListener("DOMContentLoaded", () => {
  applyFocus();
  renderProgress();
  bindRunActions();
  bindOtpForm();
  bindRunSocket();
  startRuntimeTicker();
});
