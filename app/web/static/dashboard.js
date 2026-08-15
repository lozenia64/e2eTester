// 일간 점검 대시보드 — Premium Light (HTMX card list, no Cytoscape)

(() => {
  const root = document.querySelector(".dash");
  if (!root) return;

  const REFRESH_MS = 30000;
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const DENSITY_GAP_PX = 8;
  const ROW_MIN_H = {
    comfortable: 88,
    compact: 76,
    dense: 64,
    minimal: 56,
    micro: 48,
  };
  const TIER_ORDER = ["comfortable", "compact", "dense", "minimal", "micro"];
  const $ = (sel, el = document) => el.querySelector(sel);

  let densityObs = null;
  let densityTimer = null;

  function computeDensityTier(zoneCAvail, systemCount) {
    const n = Math.max(systemCount, 1);
    const gaps = DENSITY_GAP_PX * Math.max(0, n - 1);
    for (const tier of TIER_ORDER) {
      const required = n * ROW_MIN_H[tier] + gaps;
      if (required <= zoneCAvail) return tier;
    }
    return "micro";
  }

  function measureZoneCAvail() {
    const hero = $("#dash-zone-hero", root);
    const stats = $("#dash-zone-stats", root);
    const attention = $("#dash-zone-attention", root);
    const dashStyle = getComputedStyle(root);
    const pad =
      parseFloat(dashStyle.paddingTop) + parseFloat(dashStyle.paddingBottom);
    const gap = parseFloat(dashStyle.rowGap || dashStyle.gap) || 0;
    const fixed =
      (hero?.offsetHeight || 0) +
      (stats?.offsetHeight || 0) +
      (attention?.offsetHeight || 0) +
      pad +
      gap * (attention ? 3 : 2);
    return Math.max(0, root.clientHeight - fixed);
  }

  function syncAttentionCompact() {
    const strip = $("#dash-zone-attention", root);
    if (!strip) return;
    strip.classList.toggle("dash-attention--compact", root.clientWidth < 400);
  }

  function updateDashboardDensity() {
    const container = $("#dash-zone-matrix", root);
    if (!container) return;

    const n =
      Number(container.dataset.systemCount) ||
      container.querySelectorAll(".dash-sys-row").length ||
      1;
    const zoneCAvail = measureZoneCAvail();
    const tier = computeDensityTier(zoneCAvail, n);
    container.dataset.density = tier;

    const needsScroll =
      container.scrollHeight > container.clientHeight + 1;
    container.dataset.scrollable = needsScroll ? "true" : "false";
    syncAttentionCompact();
  }

  function scheduleDensityUpdate() {
    clearTimeout(densityTimer);
    densityTimer = setTimeout(updateDashboardDensity, 50);
  }

  function bindDensityObserver() {
    if (typeof ResizeObserver === "undefined") return;
    const host = $("#dash-host-matrix", root);
    if (!host) return;

    if (!densityObs) {
      densityObs = new ResizeObserver(() => scheduleDensityUpdate());
    }
    densityObs.disconnect();
    densityObs.observe(host);
    scheduleDensityUpdate();
  }

  function animateCountUp(el, target) {
    const num = Number(target);
    if (!Number.isFinite(num)) {
      el.textContent = target;
      return;
    }
    if (REDUCED) {
      el.textContent = String(Math.round(num));
      return;
    }

    const start = performance.now();
    const duration = 600;

    function frame(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      el.textContent = String(Math.round(num * eased));
      if (t < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function runHeroCountUp() {
    const rateEl = $(".dash-hero__rate[data-target]", root);
    if (!rateEl) return;
    const target = rateEl.dataset.target;
    if (target == null) return;
    animateCountUp(rateEl, target);
  }

  function openDrawer(systemCode) {
    if (!systemCode || typeof htmx === "undefined") return;
    htmx.ajax("GET", `/api/dashboard/daily/fragments/system/${systemCode}/panel`, {
      target: "#dash-drawer-body",
      swap: "innerHTML",
    });
    window.dispatchEvent(new CustomEvent("dash-open-drawer"));
  }

  function onAfterSwap(ev) {
    if (!root.contains(ev.target) && ev.target !== root) return;
    $("#dash-error")?.classList.add("hidden");

    if (ev.target.id === "dash-host-kpi" || ev.target.closest("#dash-host-kpi")) {
      runHeroCountUp();
      syncAttentionCompact();
      scheduleDensityUpdate();
    }
    if (ev.target.id === "dash-host-matrix" || ev.target.closest("#dash-host-matrix")) {
      bindDensityObserver();
    }
  }

  document.body.addEventListener("htmx:afterSwap", onAfterSwap);

  document.body.addEventListener("htmx:responseError", (ev) => {
    const path = ev.detail?.pathInfo?.requestPath || "";
    if (!path.includes("/api/dashboard/daily")) return;
    $("#dash-error")?.classList.remove("hidden");
  });

  root.addEventListener("click", (ev) => {
    const modLink = ev.target.closest(".dash-mod--link");
    if (modLink) {
      ev.stopPropagation();
      return;
    }

    const cta = ev.target.closest(".dash-sys-row__cta");
    if (cta) {
      ev.stopPropagation();
      return;
    }

    const segLink = ev.target.closest(".dash-seg--link");
    if (segLink) {
      ev.stopPropagation();
      return;
    }

    const refreshBtn = ev.target.closest("#dash-refresh");
    if (refreshBtn) {
      refreshBtn.disabled = true;
      document.body.dispatchEvent(new CustomEvent("dash-refresh"));
      window.setTimeout(() => {
        refreshBtn.disabled = false;
      }, 600);
      return;
    }

    const row = ev.target.closest(".dash-sys-row");
    if (!row || !root.contains(row)) return;
    openDrawer(row.dataset.systemCode);
  });

  root.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    const row = ev.target.closest(".dash-sys-row");
    if (!row || !root.contains(row)) return;
    ev.preventDefault();
    openDrawer(row.dataset.systemCode);
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      document.body.dispatchEvent(new CustomEvent("dash-refresh"));
    }
  });

  window.addEventListener("resize", scheduleDensityUpdate);

  setInterval(() => {
    if (!document.hidden) {
      document.body.dispatchEvent(new CustomEvent("dash-refresh"));
    }
  }, REFRESH_MS);

  bindDensityObserver();
  runHeroCountUp();
  syncAttentionCompact();
})();
