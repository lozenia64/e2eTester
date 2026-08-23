// 일간 대시보드 페이지 엔트리. 드로어 · 새로고침 · 폴링만 맡는다.
// 밀도 계산은 CSS 컨테이너 쿼리가 담당하므로 여기 없다(설계 §3.6).
import "../components/status-hero/styles.css";
import "../components/system-matrix/styles.css";
import "../components/activity-feed/styles.css";

declare const htmx: {
  ajax: (verb: string, path: string, opts: { target: string; swap: string }) => void;
};

const REFRESH_MS = 30_000;

const root = document.querySelector<HTMLElement>(".dash");

function openDrawer(systemCode: string | undefined): void {
  if (!systemCode || typeof htmx === "undefined") return;
  htmx.ajax("GET", `/api/dashboard/daily/fragments/system/${systemCode}/panel`, {
    target: "#dash-drawer-body",
    swap: "innerHTML",
  });
  window.dispatchEvent(new CustomEvent("dash-open-drawer"));
}

function requestRefresh(): void {
  document.body.dispatchEvent(new CustomEvent("dash-refresh"));
}

// 행 안의 링크·CTA 는 드로어를 열지 않고 자기 목적지로 간다.
const PASSTHROUGH_SELECTORS = [
  ".dash-cell--link",
  ".dash-mod--link",
  ".dash-seg--link",
  ".dash-sys-row__cta",
  ".dash-activity__link",
];

function bind(dash: HTMLElement): void {
  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.target as HTMLElement | null;
    if (!target) return;
    if (!dash.contains(target) && target !== dash) return;
    document.querySelector("#dash-error")?.classList.add("hidden");
  });

  document.body.addEventListener("htmx:responseError", (event) => {
    const detail = (event as CustomEvent<{ pathInfo?: { requestPath?: string } }>).detail;
    const path = detail?.pathInfo?.requestPath ?? "";
    if (!path.includes("/api/dashboard/daily")) return;
    document.querySelector("#dash-error")?.classList.remove("hidden");
  });

  dash.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    if (!target) return;

    if (PASSTHROUGH_SELECTORS.some((sel) => target.closest(sel))) {
      event.stopPropagation();
      return;
    }

    const refreshBtn = target.closest<HTMLButtonElement>("#dash-refresh");
    if (refreshBtn) {
      refreshBtn.disabled = true;
      requestRefresh();
      window.setTimeout(() => {
        refreshBtn.disabled = false;
      }, 600);
      return;
    }

    const row = target.closest<HTMLElement>(".dash-sys-row");
    if (!row || !dash.contains(row)) return;
    openDrawer(row.dataset.systemCode);
  });

  dash.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = (event.target as HTMLElement | null)?.closest<HTMLElement>(".dash-sys-row");
    if (!row || !dash.contains(row)) return;
    event.preventDefault();
    openDrawer(row.dataset.systemCode);
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) requestRefresh();
  });

  window.setInterval(() => {
    if (!document.hidden) requestRefresh();
  }, REFRESH_MS);
}

if (root) bind(root);
