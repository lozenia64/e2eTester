// 점검 실행 화면 엔트리. 배선만 한다 — 로직은 execute/ 아래 모듈에 있다.
import { bindModuleSelectors } from "../execute/module-graph/render";
import { loadSystemBadges } from "./execute-badges";

document.addEventListener("DOMContentLoaded", () => {
  bindModuleSelectors();
  void loadSystemBadges();
});
