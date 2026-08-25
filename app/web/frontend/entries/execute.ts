// 점검 실행 화면 엔트리. 배선만 한다 — 로직은 execute/ 아래 모듈에 있다.
import { applyModuleSelection, bindModuleSelectors } from "../execute/module-graph/render";
import { getSelectedModuleIds } from "../execute/module-graph/selection";
import { loadSystemBadges } from "./execute-badges";

declare global {
  interface Window {
    __executeModuleGraph?: {
      applyModuleSelection(form: HTMLFormElement, moduleIds: string[] | null): void;
      getSelectedModuleIds(form: HTMLFormElement): string[];
    };
  }
}

// Task 3/4가 레거시 프리셋·실행 호출부를 모듈로 이관한 뒤 함께 제거한다.
// app.js가 클릭 핸들러를 등록하기 전에 준비하며, DOM 바인딩은 여기서 하지 않는다.
window.__executeModuleGraph = { applyModuleSelection, getSelectedModuleIds };

document.addEventListener("DOMContentLoaded", () => {
  bindModuleSelectors();
  void loadSystemBadges();
});
