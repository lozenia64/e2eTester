// 전 페이지 공용 엔트리. CSS 번들 + htmx/Alpine self-host.
// 외부 CDN 을 대체한다(FG-001).
// Pretendard 는 Tailwind 파이프라인(base.css) 밖의 독립 CSS 모듈로 임포트한다.
// base.css 안에서 @import 하면 패키지 CSS 의 상대 url(./woff2-dynamic-subset/*.woff2)
// 가 rebase·방출되지 않아 @font-face 가 전부 404 난다.
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "../styles/base.css";
import "../components/status-badge/styles.css";
import "../components/kpi-card/styles.css";

import Alpine from "alpinejs";
import htmx from "htmx.org";
import { normalizeTone, renderStatusBadge, statusLabel } from "../components/status-badge/index";
import { bindKpiCards } from "../components/kpi-card/index";

declare global {
  interface Window {
    Alpine: typeof Alpine;
    __statusBadge: {
      renderStatusBadge: typeof renderStatusBadge;
      normalizeTone: typeof normalizeTone;
      statusLabel: typeof statusLabel;
    };
  }
}

window.Alpine = Alpine;
window.htmx = htmx;
Alpine.start();

// 레거시 app.js 가 참조하는 다리. P3 에서 app.js 가 소멸하면 함께 제거한다.
window.__statusBadge = { renderStatusBadge, normalizeTone, statusLabel };

// htmx 가 KPI 프래그먼트를 갈아끼운 뒤에도 카운트업이 다시 걸려야 한다.
document.addEventListener("DOMContentLoaded", () => bindKpiCards());
document.body.addEventListener("htmx:afterSwap", (event) => {
  bindKpiCards((event.target as ParentNode) ?? document);
});
