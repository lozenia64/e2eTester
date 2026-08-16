// 일간 점검 대시보드 — Premium Light (HTMX card list, no Cytoscape)

(() => {
  const root = document.querySelector(".dash");
  if (!root) return;

  const REFRESH_MS = 30000;
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (sel, el = document) => el.querySelector(sel);

  const TIER_ORDER = ["comfortable", "compact", "dense", "minimal", "micro"];
  const TIER_MIN_H = {
    comfortable: 92,
    compact: 83,
    dense: 70,
    minimal: 56,
    micro: 50,
  };

  let densityObs = null;
  let densityTimer = null;

  function readContainerGapPx(container) {
    const style = getComputedStyle(container);
    return parseFloat(style.rowGap || style.gap) || 0;
  }

  function measureFlexColumnGap(container, rows) {
    const fallback = readContainerGapPx(container);
    if (!rows.length) return fallback;
    if (rows.length < 2) return fallback;
    const first = rows[0];
    const second = rows[1];
    const measured = second.offsetTop - first.offsetTop - first.offsetHeight;
    if (!Number.isFinite(measured) || measured < 0) return fallback;
    return measured;
  }

  function measurePartitionSum(container, rows, gap) {
    const heights = [...rows].map((row) => row.clientHeight);
    const sum =
      heights.reduce((acc, h) => acc + h, 0) +
      gap * Math.max(0, heights.length - 1);
    const containerH = container.clientHeight;
    return { sum, container: containerH, delta: containerH - sum };
  }

  function distributeRowHeights(n, totalRowPixels) {
    const count = Math.max(1, n);
    const available = Math.max(0, Math.floor(totalRowPixels));
    const base = Math.floor(available / count);
    const remainder = available - base * count;
    const heights = [];
    for (let i = 0; i < count; i += 1) {
      heights.push(base + (i < remainder ? 1 : 0));
    }
    return heights;
  }

  function pickTierForRowH(rowH) {
    for (const tier of TIER_ORDER) {
      if (TIER_MIN_H[tier] <= rowH - 2) return tier;
    }
    return "micro";
  }

  function tierIndex(tier) {
    const idx = TIER_ORDER.indexOf(tier);
    return idx >= 0 ? idx : TIER_ORDER.length - 1;
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

  function applyRowFlexBasis(rows, heights) {
    rows.forEach((row, index) => {
      const h = heights[index] ?? heights[heights.length - 1] ?? 0;
      row.style.flexGrow = "0";
      row.style.flexShrink = "0";
      row.style.flex = `0 0 ${h}px`;
    });
  }

  function syncRowPartition(container, n, gapHint) {
    const rows = container.querySelectorAll(".dash-sys-row");
    if (!rows.length) return;

    const rowCount = Math.min(Math.max(1, n), rows.length);
    const rowList = [...rows].slice(0, rowCount);
    void container.offsetHeight;

    let gap = measureFlexColumnGap(container, rowList);
    if (!Number.isFinite(gap) || gap < 0) {
      gap = gapHint ?? readContainerGapPx(container);
    }

    const totalGap = gap * Math.max(0, rowCount - 1);
    const available = Math.max(0, container.clientHeight - totalGap);
    let heights = distributeRowHeights(rowCount, available);
    applyRowFlexBasis(rowList, heights);
    void container.offsetHeight;

    for (let attempt = 0; attempt < 2; attempt += 1) {
      gap = measureFlexColumnGap(container, rowList);
      const { delta } = measurePartitionSum(container, rowList, gap);
      if (Math.abs(delta) <= 4) break;

      if (delta > 0) {
        const bump = Math.min(Math.floor(delta), rowCount);
        heights = heights.map((h, i) => (i < bump ? h + 1 : h));
        applyRowFlexBasis(rowList, heights);
        void container.offsetHeight;
        continue;
      }

      let excess = Math.min(Math.floor(-delta), rowCount);
      for (let i = rowCount - 1; i >= 0 && excess > 0; i -= 1) {
        if (heights[i] > 1) {
          heights[i] -= 1;
          excess -= 1;
        }
      }
      applyRowFlexBasis(rowList, heights);
      void container.offsetHeight;
    }
  }

  function applyDensityLayout(container, tier, n, gap) {
    container.dataset.density = tier;
    delete container.dataset.scrollable;
    syncRowPartition(container, n, gap);
  }

  function containerFits(container) {
    return container.scrollHeight <= container.clientHeight + 1;
  }

  function fitAndPartition(container, n) {
    syncKpiCompress();
    syncAttentionCompact();
    void container.offsetHeight;

    const gap = readContainerGapPx(container);
    const rowH = (container.clientHeight - gap * Math.max(0, n - 1)) / Math.max(n, 1);
    let tierIdx = tierIndex(pickTierForRowH(rowH));

    applyDensityLayout(container, TIER_ORDER[tierIdx], n, gap);
    void container.offsetHeight;

    let retries = 0;
    while (!containerFits(container) && tierIdx < TIER_ORDER.length - 1 && retries < 4) {
      tierIdx += 1;
      applyDensityLayout(container, TIER_ORDER[tierIdx], n, gap);
      void container.offsetHeight;
      retries += 1;
    }
  }

  function updateDashboardDensity() {
    const container = $("#dash-zone-matrix", root);
    if (!container) return;

    const n =
      Number(container.dataset.systemCount) ||
      container.querySelectorAll(".dash-sys-row").length ||
      1;

    fitAndPartition(container, n);

    requestAnimationFrame(() => {
      fitAndPartition(container, n);
      requestAnimationFrame(() => fitAndPartition(container, n));
    });
  }

  function scheduleDensityUpdate() {
    clearTimeout(densityTimer);
    densityTimer = setTimeout(updateDashboardDensity, 50);
  }

  function bindDensityObserver() {
    if (typeof ResizeObserver === "undefined") return;
    const matrixHost = $("#dash-host-matrix", root);
    const kpiHost = $("#dash-host-kpi", root);
    if (!matrixHost) return;

    if (!densityObs) {
      densityObs = new ResizeObserver(() => scheduleDensityUpdate());
    }
    densityObs.disconnect();
    densityObs.observe(matrixHost);
    if (kpiHost) densityObs.observe(kpiHost);
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
})();
