// 상황판 엔트리. Alpine·status-badge TS 를 싣지 않는다 — 조작이 없는 화면이다.
import "htmx.org";

import "../styles/wall.css";
import "../components/kpi-card/styles.css";

// 상황판의 존재 이유가 "살아있음" 이므로 일간 대시보드보다 짧게 둔다.
// 부하가 문제되면 이 상수를 늘린다(env 는 만들지 않는다 — 조절 필요가 확인되지 않았다).
const REFRESH_MS = 15_000;

// dashboard.js 와 같은 형태의 최소 구현. document.hidden 가드로 보이지 않는 탭에서는
// 요청하지 않는다.
window.setInterval(() => {
  if (!document.hidden) {
    document.body.dispatchEvent(new CustomEvent("wall-refresh"));
  }
}, REFRESH_MS);
