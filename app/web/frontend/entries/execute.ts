// 점검 실행 화면 엔트리. 배선만 한다 — 로직은 execute/ 아래 모듈에 있다.
import { bindModuleSelectors } from "../execute/module-graph/render";
import { getSelectedModuleIds } from "../execute/module-graph/selection";
import { bindPresetPanels, loadPresets } from "../execute/presets";
import { loadSystemBadges } from "./execute-badges";

declare global {
  interface Window {
    __executeModuleGraph?: {
      getSelectedModuleIds(form: HTMLFormElement): string[];
    };
  }
}

// Task 4가 남은 레거시 실행 호출부를 이관하면 제거한다.
// app.js가 클릭 핸들러를 등록하기 전에 준비하며, DOM 바인딩은 여기서 하지 않는다.
window.__executeModuleGraph = { getSelectedModuleIds };

document.addEventListener("DOMContentLoaded", () => {
  bindModuleSelectors();
  bindPresetPanels();
  void loadPresets();
  void loadSystemBadges();
});
