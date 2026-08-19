// 전 페이지 공용 엔트리. CSS 번들 + htmx/Alpine self-host.
// 외부 CDN 을 대체한다(FG-001).
import "../styles/base.css";

import Alpine from "alpinejs";
import "htmx.org";

declare global {
  interface Window {
    Alpine: typeof Alpine;
  }
}

window.Alpine = Alpine;
Alpine.start();
