// 일간 점검 대시보드 — HTMX + Cytoscape.js 라이브 파이프라인 (2026 node-canvas UI)

(() => {
  const root = document.querySelector(".dash");
  if (!root) return;

  const REFRESH_MS = 30000;
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (sel, el = document) => el.querySelector(sel);

  const TONE = {
    passed: { fill: "#10b981", ring: "#6ee7b7", label: "정상" },
    anomaly: { fill: "#f59e0b", ring: "#fcd34d", label: "이상징후" },
    error: { fill: "#ef4444", ring: "#fca5a5", label: "점검실패" },
    running: { fill: "#3b82f6", ring: "#93c5fd", label: "진행 중" },
    waiting_input: { fill: "#3b82f6", ring: "#93c5fd", label: "입력 대기" },
    blocked: { fill: "#f97316", ring: "#fdba74", label: "차단" },
    cancelled: { fill: "#f97316", ring: "#fdba74", label: "취소" },
    skipped: { fill: "#f97316", ring: "#fdba74", label: "건너뜀" },
    not_inspected: { fill: "#94a3b8", ring: "#e2e8f0", label: "미점검" },
    pending: { fill: "#94a3b8", ring: "#e2e8f0", label: "대기" },
  };

  let matrixCy = null;
  let matrixResizeObs = null;
  let matrixResizeTimer = null;

  if (typeof cytoscape !== "undefined" && typeof cytoscapeNodeHtmlLabel !== "undefined") {
    cytoscape.use(cytoscapeNodeHtmlLabel);
  }

  document.body.addEventListener("htmx:afterSwap", (ev) => {
    if (!root.contains(ev.target) && ev.target !== root) return;
    $("#dash-error")?.classList.add("hidden");
    if (ev.target.id === "dash-host-matrix" || ev.target.closest("#dash-host-matrix")) {
      renderMatrixFromPayload();
    }
  });

  document.body.addEventListener("htmx:responseError", (ev) => {
    const path = ev.detail?.pathInfo?.requestPath || "";
    if (!path.includes("/api/dashboard/daily")) return;
    $("#dash-error")?.classList.remove("hidden");
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      document.body.dispatchEvent(new CustomEvent("dash-refresh"));
      loadDateLabel();
    }
  });

  window.addEventListener("resize", () => renderMatrixFromPayload());

  setInterval(() => {
    if (!document.hidden) document.body.dispatchEvent(new CustomEvent("dash-refresh"));
  }, REFRESH_MS);

  $("#dash-refresh")?.addEventListener("click", () => {
    const btn = $("#dash-refresh");
    btn.disabled = true;
    document.body.dispatchEvent(new CustomEvent("dash-refresh"));
    setTimeout(() => {
      btn.disabled = false;
      loadDateLabel();
    }, 600);
  });

  async function loadDateLabel() {
    try {
      const res = await fetch("/api/dashboard/daily", { headers: { Accept: "application/json" } });
      if (!res.ok) return;
      const data = await res.json();
      const el = $("#dash-date");
      if (el && data.date_label) el.textContent = data.date_label;
    } catch {
      /* ignore */
    }
  }
  loadDateLabel();

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  const LAYOUT = {
    padX: 14,
    padY: 10,
    sysMinW: 124,
    sysMaxW: 168,
    modMinW: 72,
    modMaxW: 148,
    modGap: 10,
    charW: 10.5,
    modPad: 24,
    handleExtra: 4,
  };

  function textWidthPx(text) {
    return Math.ceil(String(text || "").length * LAYOUT.charW);
  }

  function sysCardWidth(name) {
    const w = 52 + textWidthPx(name);
    return Math.min(LAYOUT.sysMaxW, Math.max(LAYOUT.sysMinW, w));
  }

  function idealModWidth(label) {
    return Math.min(LAYOUT.modMaxW, Math.max(LAYOUT.modMinW, textWidthPx(label) + LAYOUT.modPad));
  }

  function modHeight(modW, label) {
    const inner = modW - LAYOUT.modPad;
    const perLine = Math.max(4, Math.floor(inner / LAYOUT.charW));
    return label.length > perLine ? 50 : 42;
  }

  /** 전체 모듈 기준 통일 크기 (가장 긴 라벨·가장 높은 노드) */
  function computeGlobalModuleSize(systems, flowLeft, flowRight) {
    const allMods = systems.flatMap((s) => s.modules || []);
    if (allMods.length === 0) {
      return { modW: LAYOUT.modMinW, modH: 42 };
    }

    let modW = allMods.reduce(
      (max, m) => Math.max(max, idealModWidth(m.name)),
      LAYOUT.modMinW,
    );
    let modH = allMods.reduce((max, m) => Math.max(max, modHeight(modW, m.name)), 42);

    const maxCount = Math.max(...systems.map((s) => (s.modules || []).length), 1);
    const avail = flowRight - flowLeft;
    const needed = modW * maxCount + LAYOUT.modGap * Math.max(0, maxCount - 1);
    if (needed > avail) {
      modW = Math.floor((avail - LAYOUT.modGap * Math.max(0, maxCount - 1)) / maxCount);
      modW = Math.max(LAYOUT.modMinW, modW);
      modH = allMods.reduce((max, m) => Math.max(max, modHeight(modW, m.name)), 42);
    }

    return { modW, modH };
  }

  function needsMultiline(label, modW) {
    return label.length * LAYOUT.charW > modW - LAYOUT.modPad;
  }

  /** 동일 modW 기준 좌→우 패킹 */
  function layoutModuleRowUniform(mods, flowLeft, flowRight, modW) {
    const n = mods.length;
    if (n === 0) return [];
    const total = modW * n + LAYOUT.modGap * (n - 1);
    const avail = flowRight - flowLeft;
    const start = flowLeft + Math.max(0, avail - total) / 2;
    let cursor = start;
    return mods.map(() => {
      const slot = { x: cursor + modW / 2 };
      cursor += modW + LAYOUT.modGap;
      return slot;
    });
  }

  function maxSysCardWidth(systems) {
    return systems.reduce((max, s) => Math.max(max, sysCardWidth(s.system_name)), LAYOUT.sysMinW);
  }

  function passAccent(rate) {
    if (rate >= 100) return "#10b981";
    if (rate >= 50) return "#6366f1";
    if (rate > 0) return "#f59e0b";
    return "#94a3b8";
  }

  function toneMeta(tone) {
    return TONE[tone] || TONE.not_inspected;
  }

  function buildElements(systems, width, height) {
    const elements = [];
    const n = Math.max(systems.length, 1);
    const rowH = Math.max(68, (height - LAYOUT.padY * 2) / n);
    const sysW = maxSysCardWidth(systems);
    const flowLeft = LAYOUT.padX + sysW + 18;
    const flowRight = width - LAYOUT.padX - LAYOUT.handleExtra;
    const laneW = width - LAYOUT.padX * 2;
    const { modW, modH } = computeGlobalModuleSize(systems, flowLeft, flowRight);

    systems.forEach((sys, si) => {
      const cy = LAYOUT.padY + rowH * (si + 0.5);
      const accent = passAccent(sys.pass_rate);
      const laneId = `lane:${sys.system_code}`;
      const sysId = `sys:${sys.system_code}`;
      const mods = sys.modules || [];

      elements.push({
        data: { id: laneId, laneW, rowH: rowH - 8, accent },
        classes: "swimlane",
        position: { x: width / 2, y: cy },
      });

      elements.push({
        data: {
          id: sysId,
          kind: "system",
          systemCode: sys.system_code,
          label: sys.system_name,
          passRate: sys.pass_rate,
          accent,
          sysW,
        },
        classes: "html system",
        position: { x: LAYOUT.padX + sysW / 2, y: cy },
      });

      const slots = layoutModuleRowUniform(mods, flowLeft, flowRight, modW);
      mods.forEach((mod, mi) => {
        const modId = `${sys.system_code}:${mod.module_id}`;
        const tone = mod.tone || "not_inspected";
        const slot = slots[mi];
        const prevId = mi === 0 ? sysId : `${sys.system_code}:${mods[mi - 1].module_id}`;
        const prevTone = mi === 0 ? "not_inspected" : mods[mi - 1].tone || "not_inspected";
        const active = tone === "passed" || prevTone === "passed";
        const flowing = tone === "running" || tone === "waiting_input";

        elements.push({
          data: {
            id: modId,
            kind: "module",
            label: mod.name,
            tone,
            runId: mod.run_id,
            statusLabel: mod.status_label,
            durationMs: mod.duration_ms,
            modW,
            modH,
            multiline: needsMultiline(mod.name, modW) ? "yes" : "no",
          },
          classes: "html module",
          position: { x: slot.x, y: cy },
        });

        elements.push({
          data: {
            id: `e:${prevId}:${modId}`,
            source: prevId,
            target: modId,
            ...(active ? { active: "yes" } : {}),
            ...(flowing ? { flowing: "yes" } : {}),
          },
        });
      });
    });

    return elements;
  }

  function nodeTemplate(data) {
    if (data.kind === "system") {
      const w = data.sysW || LAYOUT.sysMinW;
      return `<div class="dash-flow-sys" style="--accent:${esc(data.accent)};width:${w}px" title="${esc(data.label)} · 통과율 ${data.passRate}%">
        <span class="dash-flow-sys__ring">${data.passRate}%</span>
        <span class="dash-flow-sys__name">${esc(data.label)}</span>
      </div>`;
    }

    const meta = toneMeta(data.tone);
    const idle = data.tone === "not_inspected" || data.tone === "pending";
    const live = data.tone === "running" || data.tone === "waiting_input";
    const multiline = data.multiline === "yes";
    const tip = [
      data.label,
      data.statusLabel || meta.label,
      data.durationMs != null ? `소요 ${(data.durationMs / 1000).toFixed(1)}초` : null,
      data.runId ? "클릭하여 Run 상세" : null,
    ]
      .filter(Boolean)
      .join(" · ");

    return `<div class="dash-flow-node${idle ? " is-idle" : ""}${live ? " is-live" : ""}${multiline ? " is-wrap" : ""}"
      data-tone="${esc(data.tone)}"
      style="--node:${meta.fill};--ring:${meta.ring};width:${data.modW}px;height:${data.modH}px"
      title="${esc(tip)}">
      <span class="dash-flow-node__body">
        <span class="dash-flow-node__label">${esc(data.label)}</span>
      </span>
    </div>`;
  }

  function cytoscapeStyles() {
    return [
      {
        selector: ".swimlane",
        style: {
          shape: "round-rectangle",
          width: "data(laneW)",
          height: "data(rowH)",
          "background-color": "#ffffff",
          "background-opacity": 0.55,
          "border-width": 1,
          "border-color": "#e2e8f0",
          "border-opacity": 0.9,
          "z-index": 0,
          "overlay-opacity": 0,
        },
      },
      {
        selector: "node.html",
        style: {
          width: 1,
          height: 1,
          "background-opacity": 0,
          "border-opacity": 0,
          "z-index": 10,
        },
      },
      {
        selector: "node.system",
        style: { width: "data(sysW)", height: 48 },
      },
      {
        selector: "node.module",
        style: { width: "data(modW)", height: "data(modH)" },
      },
      {
        selector: "edge",
        style: {
          width: 2.5,
          "curve-style": "bezier",
          "control-point-step-size": 40,
          "target-arrow-shape": "triangle",
          "arrow-scale": 0.85,
          "line-color": "#cbd5e1",
          "target-arrow-color": "#94a3b8",
          "line-opacity": 0.55,
          "z-index": 5,
        },
      },
      {
        selector: "edge[active = 'yes']",
        style: {
          width: 3,
          "line-color": "#34d399",
          "target-arrow-color": "#10b981",
          "line-opacity": 0.85,
        },
      },
      {
        selector: "edge[flowing = 'yes']",
        style: {
          "line-style": "dashed",
          "line-dash-pattern": [6, 4],
          "line-color": "#60a5fa",
          "target-arrow-color": "#3b82f6",
          "line-opacity": 0.9,
        },
      },
      {
        selector: "node:selected",
        style: { "overlay-opacity": 0.08, "overlay-color": "#6366f1" },
      },
      {
        selector: "edge:selected",
        style: { width: 3.5, "line-color": "#818cf8" },
      },
    ];
  }

  function renderMatrixFromPayload() {
    const el = $("#dash-matrix-chart", root);
    const payloadEl = $("#dash-matrix-payload", root);
    if (!el || !payloadEl || typeof cytoscape === "undefined") return;

    let payload;
    try {
      payload = JSON.parse(payloadEl.textContent || "{}");
    } catch {
      return;
    }

    const systems = payload.systems || [];
    const w = Math.max(el.clientWidth, 320);
    const h = Math.max(el.clientHeight, 200);
    const elements = buildElements(systems, w, h);

    if (matrixCy) {
      matrixCy.destroy();
      matrixCy = null;
    }

    el.innerHTML = "";

    matrixCy = cytoscape({
      container: el,
      elements,
      style: cytoscapeStyles(),
      layout: { name: "preset", fit: false },
      minZoom: 1,
      maxZoom: 1,
      wheelSensitivity: 0,
      userZoomingEnabled: false,
      userPanningEnabled: false,
      boxSelectionEnabled: false,
      autounselectify: false,
    });

    if (typeof matrixCy.nodeHtmlLabel === "function") {
      matrixCy.nodeHtmlLabel(
        [
          {
            query: "node.html",
            halign: "center",
            valign: "center",
            cssClass: "dash-cy-html",
            tpl: nodeTemplate,
          },
        ],
        { enablePointerEvents: true },
      );
    }

    matrixCy.on("tap", "node.system", (evt) => {
      const code = evt.target.data("systemCode");
      if (code) openDrawer(code);
    });

    matrixCy.on("tap", "node.module", (evt) => {
      const runId = evt.target.data("runId");
      if (runId) window.location.href = `/runs/${runId}`;
    });

    if (!REDUCED) {
      matrixCy.elements("node.module").forEach((node, i) => {
        node.animate(
          {
            style: { opacity: 1 },
            position: node.position(),
            duration: 420,
            easing: "ease-out-cubic",
          },
          { delay: i * 35 },
        );
      });
    }

    if (!matrixResizeObs && typeof ResizeObserver !== "undefined") {
      matrixResizeObs = new ResizeObserver(() => {
        clearTimeout(matrixResizeTimer);
        matrixResizeTimer = setTimeout(() => renderMatrixFromPayload(), 150);
      });
      matrixResizeObs.observe(el);
    }
  }

  function openDrawer(systemCode) {
    if (typeof htmx === "undefined") return;
    htmx.ajax("GET", `/api/dashboard/daily/fragments/system/${systemCode}/panel`, {
      target: "#dash-drawer-body",
      swap: "innerHTML",
    });
    root.dispatchEvent(new CustomEvent("dash-open-drawer"));
  }

  function bootWhenReady() {
    if (typeof cytoscape === "undefined") {
      window.setTimeout(bootWhenReady, 50);
      return;
    }
    renderMatrixFromPayload();
  }

  bootWhenReady();
})();
