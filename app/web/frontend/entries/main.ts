// 전 페이지 공용 엔트리. CSS 번들 + htmx/Alpine self-host.
// 외부 CDN 을 대체한다(FG-001).
import "../styles/base.css";
import "../components/status-badge/styles.css";

import Alpine from "alpinejs";
import "htmx.org";
import { normalizeTone, renderStatusBadge, statusLabel } from "../components/status-badge/index";

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
Alpine.start();

// 레거시 app.js 가 참조하는 다리. P3 에서 app.js 가 소멸하면 함께 제거한다.
window.__statusBadge = { renderStatusBadge, normalizeTone, statusLabel };
