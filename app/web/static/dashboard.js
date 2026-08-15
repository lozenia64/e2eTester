// 일간 점검 대시보드 — Premium Light (HTMX card list, no Cytoscape)

(() => {
  const root = document.querySelector(".dash");
  if (!root) return;

  const REFRESH_MS = 30000;
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const DENSITY_GAP_PX = 8;
  const $ = (sel, el = document) => el.querySelector(sel);

  let densityObs = null;
  let densityTimer = null;

  function computeDensityTierFromRowH(rowH) {
    if (rowH >= 72) return "comfortable";
    if (rowH >= 56) return "compact";
    if (rowH >= 44) return "dense";
    if (rowH >= 32) return "minimal";
    return "micro";
  }

  function syncKpiCompress() {
    const kpi = $("#dash-host-kpi", root);
    if (!kpi) return;
    const limit = root.clientHeight * 0.42;
    kpi.dataset.kpiCompress = kpi.offsetHeight > limit ? "true" : "false";
  }

  function syncAttentionCompact() {
    const strip = $("#dash-zone-attention", root);
    if (!strip) return;
    strip.classList.toggle("dash-attention--compact", root.clientWidth < 400);
  }

  function syncRowPartition(container, n) {
    const rows = container.querySelectorAll(".dash-sys-row");
    if (!rows.length) return;

    const style = getComputedStyle(container);
    const gap = parseFloat(style.rowGap || style.gap) || 0;
    const rowClientH =
      (container.clientHeight - gap * Math.max(0, n - 1)) / Math.max(n, 1);

    rows.forEach((row) => {
      row.style.animation = "none";
      row.style.transform = "none";
      row.style.borderWidth = "0";
      row.style.flex = `0 0 ${rowClientH}px`;
    });
  }

  function updateDashboardDensity() {
    const container = $("#dash-zone-matrix", root);
    if (!container) return;

    const n =
      Number(container.dataset.systemCount) ||
      container.querySelectorAll(".dash-sys-row").length ||
      1;
    const gap = DENSITY_GAP_PX * Math.max(0, n - 1);
    const rowH = (container.clientHeight - gap) / Math.max(n, 1);
    container.dataset.density = computeDensityTierFromRowH(rowH);

    delete container.dataset.scrollable;
    syncRowPartition(container, n);
    syncKpiCompress();
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
    updateDashboardDensity();
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
      syncKpiCompress();
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
  updateDashboardDensity();
  runHeroCountUp();
  syncKpiCompress();
  syncAttentionCompact();
})();
