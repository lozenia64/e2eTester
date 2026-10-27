// 관리자 Run 이력 운영 콘솔 — /admin/runs 전용
(() => {
  const root = document.querySelector(".adm-runs");
  const cardGrid = document.getElementById("runs-card-grid");
  if (!root || !cardGrid) return;

  const PAGE_SIZE = 50;
  const REFRESH_MS = 30000;
  const SEARCH_DEBOUNCE_MS = 400;
  const EMPTY_HEATMAP = { users: [], systems: [], matrix: [] };
  const STORAGE_SAVED_VIEWS = "adm-runs-saved-views";

  const STATUS_BADGE = {
    PASSED: "bg-green-100 text-green-700",
    ANOMALY: "bg-amber-100 text-amber-800",
    FAILED: "bg-amber-100 text-amber-800",
    ERROR: "bg-red-100 text-red-700",
    CANCELLED: "bg-gray-100 text-gray-500",
  };

  const MODULE_STATUS_CLASS = {
    PASSED: "adm-module-timeline__item--passed",
    ANOMALY: "adm-module-timeline__item--anomaly",
    FAILED: "adm-module-timeline__item--anomaly",
    ERROR: "adm-module-timeline__item--error",
  };

  const PRESETS = [
    { id: "all", label: "전체" },
    { id: "attention", label: "주의 필요", status: "ANOMALY,ERROR" },
    { id: "today", label: "오늘", period: "today" },
    { id: "schedule", label: "예약 실행", trigger: "schedule" },
    { id: "suite", label: "전체 점검", trigger: "suite" },
  ];

  const state = {
    systems: [],
    users: [],
    board: null,
    todayStart: null,
    runs: [],
    total: 0,
    offset: 0,
    preset: "attention",
    savedViews: [],
    pendingDeleteId: null,
    drawerRun: null,
    openPopover: null,
    searchDebounceTimer: null,
    systemMapChart: null,
    systemMapShown: false,
    systemMapResizeBound: false,
    heatmapChart: null,
    heatmapResizeBound: false,
    fromFilter: "",
    toFilter: "",
    openRowMenuId: null,
    boardLoadInFlight: false,
    runsLoadInFlight: false,
  };

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
  }

  function getFilterGroupValues(group) {
    const boxes = document.querySelectorAll(`.adm-filter-option[data-group="${group}"]`);
    if (boxes.length) {
      return Array.from(boxes)
        .filter((el) => el.checked)
        .map((el) => el.value)
        .filter(Boolean);
    }
    const id = group === "system" ? "filter-system" : "filter-status";
    return getMultiSelectValues(id);
  }

  function setFilterGroupValues(group, values) {
    const wanted = new Set(values || []);
    document.querySelectorAll(`.adm-filter-option[data-group="${group}"]`).forEach((el) => {
      el.checked = wanted.has(el.value);
    });
    const id = group === "system" ? "filter-system" : "filter-status";
    setMultiSelectValues(id, values);
    updateFilterTriggerLabel(group);
  }

  function updateFilterTriggerLabel(group) {
    const btn = document.getElementById(group === "system" ? "filter-trigger-system" : "filter-trigger-status");
    if (!btn) return;
    const values = getFilterGroupValues(group);
    const base = group === "system" ? "시스템" : "상태";
    btn.textContent = values.length ? `${base} · ${values.length}` : base;
    btn.classList.toggle("has-value", values.length > 0);
  }

  function syncSegmentFromSelect(segmentId, selectId, datasetKey) {
    const value = document.getElementById(selectId)?.value || "";
    document.querySelectorAll(`#${segmentId} button`).forEach((btn) => {
      const btnValue = btn.dataset[datasetKey] ?? "";
      btn.classList.toggle("is-active", btnValue === value);
    });
  }

  function setSegmentValue(segmentId, selectId, datasetKey, value) {
    document.getElementById(selectId).value = value;
    syncSegmentFromSelect(segmentId, selectId, datasetKey);
  }

  function closeFilterPopovers(except = null) {
    document.querySelectorAll(".adm-filter-popover").forEach((panel) => {
      if (except && panel.dataset.popover === except) return;
      panel.classList.add("hidden");
    });
    document.querySelectorAll("[data-filter-popover]").forEach((btn) => {
      if (except && btn.dataset.filterPopover === except) return;
      btn.classList.remove("is-open");
      btn.setAttribute("aria-expanded", "false");
    });
    if (!except) state.openPopover = null;
  }

  function toggleFilterPopover(name) {
    const panel = document.querySelector(`[data-popover="${name}"]`);
    const btn = document.querySelector(`[data-filter-popover="${name}"]`);
    if (!panel || !btn) return;
    const willOpen = panel.classList.contains("hidden");
    closeFilterPopovers();
    if (willOpen) {
      panel.classList.remove("hidden");
      btn.classList.add("is-open");
      btn.setAttribute("aria-expanded", "true");
      state.openPopover = name;
    }
  }

  function scheduleFilterLoad() {
    if (state.searchDebounceTimer) clearTimeout(state.searchDebounceTimer);
    state.searchDebounceTimer = setTimeout(() => loadRuns({ reset: true }), SEARCH_DEBOUNCE_MS);
  }

  function renderSystemFilterOptions() {
    const wrap = document.getElementById("filter-system-options");
    const systemSelect = document.getElementById("filter-system");
    if (!wrap || !systemSelect) return;
    if (!wrap.children.length) {
      wrap.innerHTML = state.systems
        .map(
          (system) =>
            `<label class="adm-filter-option-row">
              <input type="checkbox" class="adm-filter-option" data-group="system" value="${escapeHtml(system.system_code)}" />
              <span>${escapeHtml(system.system_name || system.system_code)}</span>
            </label>`
        )
        .join("");
      if (!systemSelect.options.length) {
        state.systems.forEach((system) => {
          const option = document.createElement("option");
          option.value = system.system_code;
          option.textContent = system.system_name || system.system_code;
          systemSelect.appendChild(option);
        });
      }
    }
    const selected = new Set(getMultiSelectValues("filter-system"));
    wrap.querySelectorAll(".adm-filter-option[data-group='system']").forEach((el) => {
      el.checked = selected.has(el.value);
    });
    updateFilterTriggerLabel("system");
  }

  function getMultiSelectValues(id) {
    const el = document.getElementById(id);
    if (!el) return [];
    return Array.from(el.selectedOptions)
      .map((opt) => opt.value)
      .filter(Boolean);
  }

  function setMultiSelectValues(id, values) {
    const el = document.getElementById(id);
    if (!el) return;
    const wanted = new Set(values || []);
    Array.from(el.options).forEach((opt) => {
      if (!opt.value) return;
      opt.selected = wanted.has(opt.value);
    });
  }

  function isoToLocalInput(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function localInputToIso(value) {
    if (!value) return undefined;
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return undefined;
    return d.toISOString();
  }

  function statusLabel(value) {
    const labels = {
      PENDING: "대기",
      RUNNING: "실행 중",
      WAITING_INPUT: "입력 대기",
      PASSED: "정상",
      ANOMALY: "이상징후",
      FAILED: "이상징후",
      ERROR: "점검실패",
      CANCELLED: "취소",
    };
    return labels[value] || value;
  }

  function systemLabels(codes) {
    const select = document.getElementById("filter-system");
    if (!select) return codes.join(", ");
    const byCode = new Map(Array.from(select.options).map((opt) => [opt.value, opt.textContent]));
    return codes.map((code) => byCode.get(code) || code).join(", ");
  }

  function showToast(message, tone = "info") {
    const container = document.getElementById("toast-container");
    if (!container) {
      window.alert(message);
      return;
    }
    const el = document.createElement("div");
    const toneClass =
      tone === "error"
        ? "border-red-200 bg-red-50 text-red-800"
        : tone === "success"
          ? "border-green-200 bg-green-50 text-green-800"
          : "border-gray-200 bg-white text-gray-800";
    el.className = `rounded-lg border px-4 py-3 text-sm shadow-lg ${toneClass}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  function formatDuration(startedAt, endedAt) {
    if (!startedAt || !endedAt) return "—";
    const sec = Math.max(0, Math.floor((new Date(endedAt) - new Date(startedAt)) / 1000));
    if (sec < 60) return `${sec}초`;
    const min = Math.floor(sec / 60);
    const rem = sec % 60;
    return rem ? `${min}분 ${rem}초` : `${min}분`;
  }

  function formatWhen(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    const now = Date.now();
    const diff = now - d.getTime();
    const min = Math.floor(diff / 60000);
    let rel = "";
    if (min < 1) rel = "방금";
    else if (min < 60) rel = `${min}분 전`;
    else if (min < 1440) rel = `${Math.floor(min / 60)}시간 전`;
    else rel = `${Math.floor(min / 1440)}일 전`;
    return `${rel} · ${d.toLocaleString("ko-KR")}`;
  }

  function triggerLabel(value) {
    if (value === "schedule") return "예약";
    if (value === "suite") return "전체 점검";
    return "수동";
  }

  function triggerBadgeClass(value) {
    if (value === "schedule") return "bg-sky-100 text-sky-700";
    if (value === "suite") return "bg-violet-100 text-violet-700";
    return "bg-gray-100 text-gray-600";
  }

  function periodToQuery(period) {
    if (!period) return {};
    if (period === "today") {
      if (state.todayStart) return { from: state.todayStart };
      return { from: new Date().toISOString() };
    }
    const days = period === "7d" ? 7 : period === "30d" ? 30 : 0;
    if (!days) return {};
    if (state.todayStart) {
      const anchor = new Date(state.todayStart);
      const from = new Date(anchor.getTime() - (days - 1) * 86400000);
      return { from: from.toISOString() };
    }
    const now = new Date();
    return { from: new Date(now.getTime() - days * 86400000).toISOString() };
  }

  function readFiltersFromDom() {
    const systemCodes = getFilterGroupValues("system");
    const statuses = getFilterGroupValues("status");
    const trigger = document.getElementById("filter-trigger").value;
    const period = document.getElementById("filter-period").value;
    const userId = document.getElementById("filter-user").value;
    const userName = document.getElementById("filter-user-name").value.trim();
    const runId = document.getElementById("filter-run-id").value.trim();
    const periodQuery = periodToQuery(period);
    const from =
      periodQuery.from ||
      localInputToIso(document.getElementById("filter-from-dt").value) ||
      state.fromFilter ||
      undefined;
    const to =
      (!period && localInputToIso(document.getElementById("filter-to-dt").value)) ||
      state.toFilter ||
      undefined;
    return {
      system_codes: systemCodes,
      statuses,
      triggered_by: trigger || undefined,
      user_id: userId || undefined,
      user_name: userName || undefined,
      run_id: runId || undefined,
      period: period || undefined,
      from: from || undefined,
      to: to || undefined,
    };
  }

  function applyFiltersToDom(filters) {
    setFilterGroupValues("system", filters.system_codes || []);
    setFilterGroupValues("status", filters.statuses || []);
    document.getElementById("filter-trigger").value = filters.triggered_by || "";
    document.getElementById("filter-period").value = filters.period || "";
    syncSegmentFromSelect("filter-trigger-segment", "filter-trigger", "triggerValue");
    syncSegmentFromSelect("filter-period-segment", "filter-period", "periodValue");
    document.getElementById("filter-user").value = filters.user_id || "";
    document.getElementById("filter-user-name").value = filters.user_name || "";
    document.getElementById("filter-run-id").value = filters.run_id || "";
    if (filters.period) {
      state.fromFilter = "";
      state.toFilter = "";
      document.getElementById("filter-from-dt").value = "";
      document.getElementById("filter-to-dt").value = "";
    } else {
      state.fromFilter = filters.from || "";
      state.toFilter = filters.to || "";
      document.getElementById("filter-from-dt").value = isoToLocalInput(state.fromFilter);
      document.getElementById("filter-to-dt").value = isoToLocalInput(state.toFilter);
    }
  }

  function clearCustomDateFilters() {
    state.fromFilter = "";
    state.toFilter = "";
    document.getElementById("filter-from-dt").value = "";
    document.getElementById("filter-to-dt").value = "";
  }

  function captureViewState() {
    const filters = readFiltersFromDom();
    return {
      preset: state.preset,
      filters: {
        system_codes: filters.system_codes || [],
        statuses: filters.statuses || [],
        triggered_by: filters.triggered_by || "",
        period: filters.period || "",
        user_id: filters.user_id || "",
        user_name: filters.user_name || "",
        run_id: filters.run_id || "",
        from: filters.from || "",
        to: filters.to || "",
      },
    };
  }

  function loadSavedViews() {
    try {
      const raw = localStorage.getItem(STORAGE_SAVED_VIEWS);
      state.savedViews = raw ? JSON.parse(raw) : [];
    } catch (_) {
      state.savedViews = [];
    }
  }

  function persistSavedViews() {
    localStorage.setItem(STORAGE_SAVED_VIEWS, JSON.stringify(state.savedViews));
  }

  function renderSavedViews() {
    const wrap = document.getElementById("runs-saved-views");
    if (!wrap) return;
    wrap.innerHTML = state.savedViews
      .map(
        (view) =>
          `<span class="adm-saved-view" data-saved-view="${escapeHtml(view.id)}">
            <span>${escapeHtml(view.name)}</span>
            <button type="button" data-delete-view="${escapeHtml(view.id)}" aria-label="저장 뷰 삭제">×</button>
          </span>`
      )
      .join("");
  }

  function saveCurrentView() {
    const name = window.prompt("저장할 뷰 이름을 입력하세요");
    if (!name || !name.trim()) return;
    const view = {
      id: `view_${Date.now()}`,
      name: name.trim(),
      ...captureViewState(),
    };
    state.savedViews = [view, ...state.savedViews].slice(0, 12);
    persistSavedViews();
    renderSavedViews();
    showToast("뷰가 저장되었습니다.", "success");
  }

  function applySavedView(viewId) {
    const view = state.savedViews.find((item) => item.id === viewId);
    if (!view) return;
    state.preset = view.preset || "all";
    applyFiltersToDom(view.filters || {});
    if (state.preset === "attention") {
      setFilterGroupValues("status", []);
      document.getElementById("filter-period").value = view.filters?.period || "7d";
      syncSegmentFromSelect("filter-period-segment", "filter-period", "periodValue");
    }
    renderPresets();
    loadRuns({ reset: true });
  }

  function buildRunsQuery(offset = 0, { forExport = false } = {}) {
    const params = new URLSearchParams();
    if (!forExport) {
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(offset));
      params.set("include_total", "true");
    }
    const filters = readFiltersFromDom();
    if (state.preset === "attention") {
      params.append("status", "ANOMALY");
      params.append("status", "ERROR");
      params.append("status", "FAILED");
    } else {
      filters.statuses.forEach((status) => params.append("status", status));
    }
    filters.system_codes.forEach((code) => params.append("system_code", code));
    if (filters.triggered_by) params.set("triggered_by", filters.triggered_by);
    if (filters.user_id) params.set("user_id", filters.user_id);
    if (filters.user_name) params.set("user_name", filters.user_name);
    if (filters.run_id) params.set("run_id", filters.run_id);
    if (filters.from) params.set("from", filters.from);
    if (filters.to) params.set("to", filters.to);
    return params.toString();
  }

  function syncUrl() {
    const params = new URLSearchParams();
    const filters = readFiltersFromDom();
    if (state.preset && state.preset !== "all") params.set("preset", state.preset);
    if (filters.period) params.set("period", filters.period);
    filters.system_codes.forEach((code) => params.append("system_code", code));
    if (state.preset !== "attention") {
      filters.statuses.forEach((status) => params.append("status", status));
    }
    ["triggered_by", "user_id", "user_name", "run_id"].forEach((key) => {
      if (filters[key]) params.set(key, filters[key]);
    });
    if (!filters.period) {
      if (filters.from) params.set("from", filters.from);
      if (filters.to) params.set("to", filters.to);
    }
    const qs = params.toString();
    window.history.replaceState(null, "", qs ? `${window.location.pathname}?${qs}` : window.location.pathname);
  }

  function restoreFromUrl() {
    const params = new URLSearchParams(window.location.search);
    if (!params.toString()) return false;
    if (params.get("preset")) state.preset = params.get("preset");
    const urlPeriod = params.get("period") || "";
    const urlFrom = params.get("from") || "";
    const urlTo = params.get("to") || "";
    state.fromFilter = urlPeriod ? "" : urlFrom;
    state.toFilter = urlPeriod ? "" : urlTo;
    applyFiltersToDom({
      system_codes: params.getAll("system_code"),
      statuses: params.getAll("status"),
      triggered_by: params.get("triggered_by") || "",
      period: urlPeriod,
      user_id: params.get("user_id") || "",
      user_name: params.get("user_name") || "",
      run_id: params.get("run_id") || "",
      from: state.fromFilter,
      to: state.toFilter,
    });
    if (state.preset === "attention" && !urlPeriod) {
      document.getElementById("filter-period").value = "7d";
      clearCustomDateFilters();
    }
    renderPresets();
    syncSegmentFromSelect("filter-trigger-segment", "filter-trigger", "triggerValue");
    syncSegmentFromSelect("filter-period-segment", "filter-period", "periodValue");
    updateFilterTriggerLabel("system");
    updateFilterTriggerLabel("status");
    return true;
  }

  function applyPreset(presetId) {
    state.preset = presetId;
    const preset = PRESETS.find((item) => item.id === presetId) || PRESETS[0];
    setFilterGroupValues("status", preset.status ? preset.status.split(",") : []);
    setSegmentValue("filter-trigger-segment", "filter-trigger", "triggerValue", preset.trigger || "");
    setSegmentValue("filter-period-segment", "filter-period", "periodValue", preset.period || "");
    if (preset.period) clearCustomDateFilters();
    if (preset.id === "attention") {
      setFilterGroupValues("status", []);
      setSegmentValue("filter-period-segment", "filter-period", "periodValue", "7d");
      clearCustomDateFilters();
    }
    renderPresets();
  }

  function renderPresets() {
    const wrap = document.getElementById("runs-presets");
    wrap.innerHTML = PRESETS.map(
      (p) =>
        `<button type="button" class="adm-chip${state.preset === p.id ? " is-active" : ""}" data-preset="${p.id}">${escapeHtml(p.label)}</button>`
    ).join("");
  }

  function renderActiveFilters() {
    const wrap = document.getElementById("runs-active-filters");
    const chips = [];
    if (state.preset && state.preset !== "all") {
      const preset = PRESETS.find((p) => p.id === state.preset);
      if (preset) chips.push({ key: "preset", label: `프리셋: ${preset.label}` });
    }
    const systemCodes = getFilterGroupValues("system");
    if (systemCodes.length) {
      chips.push({ key: "system", label: `시스템: ${systemLabels(systemCodes)}` });
    }
    const statusCodes = getFilterGroupValues("status");
    if (statusCodes.length) {
      chips.push({ key: "status", label: `상태: ${statusCodes.map(statusLabel).join(", ")}` });
    }
    const triggerSel = document.getElementById("filter-trigger");
    if (triggerSel.value) {
      chips.push({ key: "trigger", label: `트리거: ${triggerSel.options[triggerSel.selectedIndex].text}` });
    }
    const periodSel = document.getElementById("filter-period");
    if (periodSel.value) {
      chips.push({ key: "period", label: `기간: ${periodSel.options[periodSel.selectedIndex].text}` });
    } else if (state.fromFilter || state.toFilter) {
      if (state.fromFilter) {
        chips.push({ key: "from", label: `시작: ${new Date(state.fromFilter).toLocaleString("ko-KR")}` });
      }
      if (state.toFilter) {
        chips.push({ key: "to", label: `종료: ${new Date(state.toFilter).toLocaleString("ko-KR")}` });
      }
    }
    const userSel = document.getElementById("filter-user");
    if (userSel.value) {
      chips.push({ key: "user", label: `실행자: ${userSel.options[userSel.selectedIndex].text}` });
    }
    const userNameInput = document.getElementById("filter-user-name");
    if (userNameInput.value.trim()) {
      chips.push({ key: "user_name", label: `이름: ${userNameInput.value.trim()}` });
    }
    const runIdInput = document.getElementById("filter-run-id");
    if (runIdInput.value.trim()) {
      chips.push({ key: "run_id", label: `Run ID: ${runIdInput.value.trim()}` });
    }
    wrap.innerHTML = chips
      .map(
        (chip) =>
          `<span class="adm-filter-chip">${escapeHtml(chip.label)}<button type="button" data-clear="${chip.key}" aria-label="필터 제거">×</button></span>`
      )
      .join("");
  }

  const HEATMAP_VALUE_LABEL = {
    "-1": "없음",
    0: "정상",
    1: "이상징후",
    2: "점검실패",
    3: "취소",
  };

  function heatmapWrapHeight(userCount, systemCount) {
    const rows = Math.max(userCount, 1);
    const cols = Math.max(systemCount, 1);
    const height = 56 + rows * 30 + (cols > 4 ? 24 : 0);
    return Math.min(28 * 16, Math.max(12 * 16, height));
  }

  function syncHeatmapWrapHeight(userCount, systemCount) {
    const wrap = document.querySelector(".adm-heatmap-wrap");
    if (!wrap) return;
    wrap.style.height = `${heatmapWrapHeight(userCount, systemCount)}px`;
  }

  function queueHeatmapResize() {
    if (!state.heatmapChart) return;
    requestAnimationFrame(() => {
      state.heatmapChart?.resize();
      requestAnimationFrame(() => state.heatmapChart?.resize());
    });
  }

  function renderHeatmapFallback(payload) {
    const canvas = document.getElementById("runs-heatmap-canvas");
    const fallback = document.getElementById("runs-heatmap-fallback");
    if (canvas) canvas.classList.add("hidden");
    if (!fallback) return;
    fallback.classList.remove("hidden");
    const users = payload.users || [];
    const systems = payload.systems || [];
    const matrix = payload.matrix || [];
    if (!users.length || !systems.length) {
      fallback.innerHTML = '<p class="py-6 text-center text-xs text-gray-400">히트맵 데이터 없음</p>';
      return;
    }
    let html = "<table><thead><tr><th></th>";
    systems.forEach((name) => {
      html += `<th>${escapeHtml(name)}</th>`;
    });
    html += "</tr></thead><tbody>";
    users.forEach((user, rowIndex) => {
      html += `<tr><th>${escapeHtml(user)}</th>`;
      systems.forEach((_name, colIndex) => {
        const value = matrix[rowIndex]?.[colIndex] ?? -1;
        const label = HEATMAP_VALUE_LABEL[String(value)] || "—";
        html += `<td data-value="${value}" title="${escapeHtml(label)}"></td>`;
      });
      html += "</tr>";
    });
    html += "</tbody></table>";
    fallback.innerHTML = html;
  }

  function renderHeatmap(payload) {
    const el = document.getElementById("runs-heatmap-canvas");
    const fallback = document.getElementById("runs-heatmap-fallback");
    if (!el || typeof echarts === "undefined") {
      renderHeatmapFallback(payload);
      return;
    }
    fallback?.classList.add("hidden");
    el.classList.remove("hidden");
    const users = payload.users || [];
    const systems = payload.systems || [];
    const matrix = payload.matrix || [];
    syncHeatmapWrapHeight(users.length, systems.length);

    const rect = el.getBoundingClientRect();
    if (state.heatmapChart && (rect.width < 80 || rect.height < 80)) {
      state.heatmapChart.dispose();
      state.heatmapChart = null;
    }
    if (!state.heatmapChart) {
      state.heatmapChart = echarts.init(el);
      if (!state.heatmapResizeBound) {
        state.heatmapResizeBound = true;
        window.addEventListener("resize", () => state.heatmapChart?.resize());
      }
    }
    const data = [];
    for (let y = 0; y < users.length; y += 1) {
      for (let x = 0; x < systems.length; x += 1) {
        data.push([x, y, matrix[y]?.[x] ?? -1]);
      }
    }
    const rotateLabels = systems.length > 4 ? 35 : 0;
    state.heatmapChart.setOption(
      {
        tooltip: {
          position: "top",
          formatter(params) {
            const user = users[params.value[1]] || "";
            const system = systems[params.value[0]] || "";
            const label = HEATMAP_VALUE_LABEL[String(params.value[2])] || "—";
            return `${user}<br/>${system}<br/>${label}`;
          },
        },
        grid: { top: 12, left: 8, right: 12, bottom: 52, containLabel: true },
        xAxis: {
          type: "category",
          data: systems,
          splitArea: { show: true },
          axisLabel: { fontSize: 10, interval: 0, rotate: rotateLabels },
        },
        yAxis: {
          type: "category",
          data: users,
          splitArea: { show: true },
          axisLabel: { fontSize: 10, width: 96, overflow: "truncate" },
        },
        visualMap: {
          type: "piecewise",
          orient: "horizontal",
          left: "center",
          bottom: 4,
          itemWidth: 12,
          itemHeight: 12,
          itemGap: 8,
          textStyle: { fontSize: 10 },
          pieces: (payload.legend || []).map((item) => ({
            value: item.value,
            label: item.label,
            color: item.color,
          })),
        },
        series: [
          {
            type: "heatmap",
            data,
            label: { show: false },
            emphasis: { itemStyle: { shadowBlur: 6, shadowColor: "rgba(0,0,0,0.15)" } },
          },
        ],
      },
      true
    );
    queueHeatmapResize();
  }

  function moduleSummary(run) {
    const passed = run.module_passed ?? 0;
    const total = run.module_total ?? 0;
    let text = `통과 ${passed}/${total}`;
    if (run.module_skipped) text += ` · 제외 ${run.module_skipped}`;
    if (run.failed_module_name) {
      const kind = run.status === "ERROR" ? "점검실패" : "이상징후";
      text += ` · ${kind}: ${run.failed_module_name}`;
    }
    return text;
  }

  function comparisonBadgesHtml(run) {
    const comparison = run.comparison;
    if (!comparison?.badges?.length) return "";
    return comparison.badges
      .map((badge) => {
        if (badge === "recovered") {
          const count = comparison.recovered?.length || 0;
          const label = count > 0 ? `회복 ${count}` : "회복";
          return `<span class="adm-comparison-badge adm-comparison-badge--recovered">${escapeHtml(label)}</span>`;
        }
        if (badge === "new_failure") {
          const count = comparison.newly_failed?.length || 0;
          const label = count > 0 ? `신규 실패 ${count}` : "신규 실패";
          return `<span class="adm-comparison-badge adm-comparison-badge--new_failure">${escapeHtml(label)}</span>`;
        }
        if (badge === "still_failing") {
          const count = comparison.still_failing?.length || 0;
          const label = count > 0 ? `지속 실패 ${count}` : "지속 실패";
          return `<span class="adm-comparison-badge adm-comparison-badge--still_failing">${escapeHtml(label)}</span>`;
        }
        return "";
      })
      .join("");
  }

  function comparisonDrawerHtml(run) {
    const comparison = run.comparison;
    if (!comparison) return "";
    const chips = [];
    if (comparison.newly_failed?.length) {
      chips.push(
        `<span class="adm-comparison-badge adm-comparison-badge--new_failure">신규 실패: ${escapeHtml(comparison.newly_failed.join(", "))}</span>`
      );
    }
    if (comparison.recovered?.length) {
      chips.push(
        `<span class="adm-comparison-badge adm-comparison-badge--recovered">회복: ${escapeHtml(comparison.recovered.join(", "))}</span>`
      );
    }
    if (comparison.still_failing?.length) {
      chips.push(
        `<span class="adm-comparison-badge adm-comparison-badge--still_failing">지속 실패: ${escapeHtml(comparison.still_failing.join(", "))}</span>`
      );
    }
    if (!chips.length) return "";
    return `<div class="flex flex-wrap gap-2">${chips.join("")}</div>`;
  }

  function updateRunsUpdatedAt(iso) {
    const el = document.getElementById("runs-updated-at");
    if (!el) return;
    if (!iso) {
      el.textContent = "";
      return;
    }
    try {
      const when = new Date(iso).toLocaleString("ko-KR");
      el.textContent = `갱신 ${when} · 30초`;
    } catch (_) {
      el.textContent = "갱신 완료 · 30초";
    }
  }

  function closeRowMenus(exceptRunId = null) {
    document.querySelectorAll("[data-row-menu]").forEach((menu) => {
      if (exceptRunId && menu.dataset.rowMenu === exceptRunId) return;
      menu.classList.add("hidden");
    });
    if (!exceptRunId) state.openRowMenuId = null;
  }

  function toggleRowMenu(runId) {
    const menu = document.querySelector(`[data-row-menu="${runId}"]`);
    if (!menu) return;
    const willOpen = menu.classList.contains("hidden");
    closeRowMenus();
    if (willOpen) {
      menu.classList.remove("hidden");
      state.openRowMenuId = runId;
    }
  }

  function rowActionMenuHtml(run) {
    const canDelete = !["RUNNING", "PENDING", "WAITING_INPUT"].includes(run.status);
    const anomalyItem = ["ANOMALY", "ERROR", "FAILED"].includes(run.status)
      ? `<a href="/anomalies?system=${encodeURIComponent(run.system_code)}" class="adm-row-menu__item">이상징후</a>`
      : "";
    const deleteItem = canDelete
      ? `<button type="button" class="adm-row-menu__item adm-row-menu__item--danger" data-row-action="delete" data-run-id="${escapeHtml(run.run_id)}">삭제</button>`
      : "";
    return `<div class="adm-row-menu" data-row-action-cell>
      <button type="button" class="adm-row-menu__btn" data-row-menu-toggle="${escapeHtml(run.run_id)}" aria-label="행 메뉴">⋯</button>
      <div class="adm-row-menu__dropdown hidden" data-row-menu="${escapeHtml(run.run_id)}">
        <button type="button" class="adm-row-menu__item" data-row-action="detail" data-run-id="${escapeHtml(run.run_id)}">상세</button>
        ${anomalyItem}
        ${deleteItem}
      </div>
    </div>`;
  }

  function statusCardClass(status) {
    if (status === "PASSED") return "passed";
    if (status === "ANOMALY" || status === "FAILED") return "anomaly";
    if (status === "ERROR") return "error";
    if (status === "CANCELLED") return "cancelled";
    return "";
  }

  function renderRunCard(run) {
    const cls = STATUS_BADGE[run.status] || "bg-gray-100 text-gray-600";
    const cardCls = statusCardClass(run.status);
    return `<article class="adm-run-card adm-run-card--${cardCls}" data-run-id="${escapeHtml(run.run_id)}">
      <div class="adm-run-card__accent" aria-hidden="true"></div>
      <div class="adm-run-card__inner">
        <div class="adm-run-card__head">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class="rounded-md bg-indigo-50 px-1.5 py-0.5 font-mono text-[10px] font-bold text-indigo-700 ring-1 ring-indigo-100">${escapeHtml(String(run.system_code || "").toUpperCase())}</span>
              <span class="text-sm font-bold text-gray-900 truncate">${escapeHtml(run.system_name || run.system_code)}</span>
            </div>
            <p class="mt-1 text-xs text-gray-500 line-clamp-2">${escapeHtml(moduleSummary(run))}</p>
            <div class="mt-1.5 flex flex-wrap gap-1">${comparisonBadgesHtml(run)}</div>
            <p class="mt-1.5 font-mono text-[10px] text-gray-400 truncate">${escapeHtml(run.run_id)}</p>
          </div>
          <div class="flex shrink-0 flex-col items-end gap-1">
            <span class="inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${cls}">${escapeHtml(run.status_label || run.status)}</span>
            ${rowActionMenuHtml(run)}
          </div>
        </div>
        <div class="adm-run-card__meta">
          <span class="inline-flex rounded-full px-2 py-0.5 font-semibold ${triggerBadgeClass(run.triggered_by)}">${escapeHtml(triggerLabel(run.triggered_by))}</span>
          <span>${escapeHtml(run.created_by_user_name || "(시스템)")}</span>
          <span>${escapeHtml(formatDuration(run.started_at, run.ended_at))}</span>
          <span>${escapeHtml(formatWhen(run.requested_at).split(" · ")[0])}</span>
        </div>
      </div>
    </article>`;
  }

  function renderRunsList() {
    if (!state.runs.length) {
      cardGrid.innerHTML = '<p class="adm-run-card__empty">조건에 맞는 Run 없음</p>';
      return;
    }
    cardGrid.innerHTML = state.runs.map((run) => renderRunCard(run)).join("");
  }

  function updatePageMeta() {
    const shown = state.runs.length;
    document.getElementById("runs-result-meta").textContent =
      state.total > 0 ? `전체 ${state.total.toLocaleString()}건` : "";
    document.getElementById("runs-page-meta").textContent =
      shown > 0 ? `${shown.toLocaleString()}건 표시 (전체 ${state.total.toLocaleString()}건)` : "";
    const moreBtn = document.getElementById("btn-load-more");
    if (shown < state.total) moreBtn.classList.remove("hidden");
    else moreBtn.classList.add("hidden");
  }

  async function loadHeatmap() {
    try {
      const res = await fetch("/api/admin/runs/heatmap");
      if (!res.ok) throw new Error("heatmap");
      return await res.json();
    } catch (_) {
      return null;
    }
  }

  function renderHeatmapPanel(payload) {
    if (payload) renderHeatmap(payload);
    else renderHeatmapFallback(EMPTY_HEATMAP);
  }

  // 이상징후 비율 경계 → 상태 색 토큰. 0% 정상 · 5% 이상징후 · 10% 이상 점검실패 색(설계 §4.3).
  // 색 값은 tokens.generated.css 의 SSOT(app/core/status_colors.py)를 읽는다 — ECharts 는 CSS 변수를 모른다.
  const SYSTEM_MAP_COLOR_STOPS = [
    [0, "passed"],
    [0.05, "anomaly"],
    [0.1, "error"],
  ];
  const SYSTEM_MAP_INTRO_MS = 1400;

  function cssToken(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function statusRgb(tone) {
    const hex = /^#([0-9a-f]{6})$/i.exec(cssToken(`--st-${tone}-solid`))?.[1] || "64748b";
    return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
  }

  let systemMapStops = null;

  function anomalyColor(rate) {
    systemMapStops ||= SYSTEM_MAP_COLOR_STOPS.map(([at, tone]) => [at, statusRgb(tone)]);
    const stops = systemMapStops;
    const r = Math.min(Math.max(rate, 0), stops[stops.length - 1][0]);
    let i = 1;
    while (i < stops.length - 1 && r > stops[i][0]) i += 1;
    const [r0, c0] = stops[i - 1];
    const [r1, c1] = stops[i];
    const t = (r - r0) / (r1 - r0);
    const rgb = c0.map((v, k) => Math.round(v + (c1[k] - v) * t));
    return `rgb(${rgb.join(",")})`;
  }

  function prefersReducedMotion() {
    return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  }

  function anomalyRate(system) {
    return system.runs ? system.anomaly / system.runs : 0;
  }

  function formatPercent(rate) {
    return `${(rate * 100).toFixed(1)}%`;
  }

  // 시스템명 뒤에 조사를 붙이지 않는다 — '챗봇(모바일)' 같은 이름에서 조사가 어긋난다.
  function systemMapSummaryHtml(map, progress = 1) {
    const byCode = Object.fromEntries((map.systems || []).map((s) => [s.system_code, s]));
    const topRuns = byCode[map.top_runs];
    const topAnomaly = byCode[map.top_anomaly];
    if (!topRuns) return "";
    const count = (value) => `<span class="adm-sysmap__num">${Math.round(value * progress).toLocaleString()}</span>`;
    const head = `이번 달 가장 많이 돈 건 <b>${escapeHtml(topRuns.system_name)}</b>(${count(topRuns.runs)}회)`;
    if (!topAnomaly) return `${head}입니다. 이번 달 이상징후는 아직 없습니다.`;
    return `${head}, 이상징후가 가장 많은 건 <b>${escapeHtml(topAnomaly.system_name)}</b>(${count(topAnomaly.anomaly)}건)입니다.`;
  }

  function systemMapSummaryText(map) {
    const div = document.createElement("div");
    div.innerHTML = systemMapSummaryHtml(map);
    return div.textContent || "";
  }

  // progress 0→1: 타일 면적이 균등 격자에서 실제 비율로 펼쳐지고 숫자가 0에서 올라간다.
  function systemMapSeriesData(map, progress) {
    const systems = map.systems || [];
    const even = systems.reduce((sum, s) => sum + s.runs, 0) / Math.max(systems.length, 1);
    return systems.map((s) => {
      const isTopAnomaly = s.system_code === map.top_anomaly;
      return {
        name: s.system_name,
        value: even + (s.runs - even) * progress,
        systemCode: s.system_code,
        runsShown: Math.round(s.runs * progress),
        anomalyShown: Math.round(s.anomaly * progress),
        rate: anomalyRate(s),
        badge: isTopAnomaly ? "최다 이상징후" : s.system_code === map.top_runs ? "최다 실행" : "",
        itemStyle: { color: anomalyColor(anomalyRate(s)) },
      };
    });
  }

  function systemMapOption(map, progress) {
    const panel = cssToken("--c-ink-950");
    const white = cssToken("--c-white");
    return {
      animation: false,
      tooltip: {
        formatter(params) {
          const d = params.data || {};
          return `<b>${escapeHtml(params.name)}</b><br/>실행 ${(d.runsShown ?? 0).toLocaleString()}회<br/>이상징후 ${d.anomalyShown ?? 0}건 · ${formatPercent(d.rate || 0)}<br/><span style="color:var(--c-gray-400)">클릭하면 아래에서 Run을 봅니다</span>`;
        },
      },
      series: [
        {
          type: "treemap",
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          // 루트 레벨 기본 테두리가 흰색이라 패널 배경색으로 덮는다.
          levels: [{ itemStyle: { borderWidth: 0, gapWidth: 6, borderColor: panel } }],
          itemStyle: { borderWidth: 0, borderRadius: 12 },
          label: {
            show: true,
            position: "insideTopLeft",
            padding: [10, 12],
            formatter(params) {
              const d = params.data;
              const badge = d.badge ? `{badge|${d.badge}}\n` : "";
              return `${badge}{name|${params.name}}\n{num|${d.runsShown.toLocaleString()}회}\n{sub|이상징후 ${d.anomalyShown}건 · ${formatPercent(d.rate)}}`;
            },
            rich: {
              badge: {
                color: panel,
                backgroundColor: "rgba(255,255,255,0.92)",
                borderRadius: 999,
                padding: [3, 8],
                fontSize: 11,
                fontWeight: 700,
              },
              name: { color: white, fontSize: 15, fontWeight: 700, lineHeight: 26 },
              num: { color: white, fontSize: 26, fontWeight: 900, lineHeight: 34 },
              sub: { color: "rgba(255,255,255,0.88)", fontSize: 12, lineHeight: 18 },
            },
          },
          data: systemMapSeriesData(map, progress),
        },
      ],
    };
  }

  function renderSystemMapTable(map) {
    const body = document.getElementById("runs-system-map-table");
    if (!body) return;
    body.innerHTML = (map.systems || [])
      .map(
        (s) =>
          `<tr><th scope="row">${escapeHtml(s.system_name)}</th><td>${s.runs.toLocaleString()}</td><td>${s.anomaly.toLocaleString()}</td><td>${formatPercent(anomalyRate(s))}</td></tr>`
      )
      .join("");
  }

  // 집계는 Run 기록 기준이라 레지스트리에서 빠진 시스템 타일도 있다 — 체크박스가 없으면 필터가 사라진다.
  function ensureSystemFilterOption(code, name) {
    if (state.systems.some((item) => item.system_code === code)) return;
    state.systems.push({ system_code: code, system_name: name || code });
    document.getElementById("filter-system-options").innerHTML = "";
    document.getElementById("filter-system").innerHTML = "";
    renderSystemFilterOptions();
  }

  function focusExploreOnSystem(code) {
    const map = state.board?.system_map || {};
    const period = map.period || {};
    const system = (map.systems || []).find((item) => item.system_code === code);
    ensureSystemFilterOption(code, system?.system_name);
    // 상한(to)은 두지 않는다 — datetime-local 이 분 단위로 잘라 그 분의 Run 이 빠진다.
    applyFiltersToDom({
      system_codes: [code],
      statuses: ["PASSED", "ANOMALY"],
      from: period.from,
    });
    state.preset = "all";
    renderPresets();
    loadRuns({ reset: true });
    // smooth 는 일부 내장 브라우저(Orca)에서 무시돼 화면이 안 움직인다 — 즉시 이동.
    document.getElementById("runs-explore")?.scrollIntoView({ block: "start" });
  }

  function renderSystemMap(map, { animate = false } = {}) {
    const panel = document.getElementById("runs-system-map");
    const el = document.getElementById("runs-system-map-chart");
    const summary = document.getElementById("runs-system-map-summary");
    const empty = document.getElementById("runs-system-map-empty");
    if (!panel || !el || !summary || !map) return;
    const hasData = (map.systems || []).length > 0;
    el.classList.toggle("hidden", !hasData);
    empty?.classList.toggle("hidden", hasData);
    renderSystemMapTable(map);
    if (!hasData) {
      summary.innerHTML = "";
      state.systemMapChart?.dispose();
      state.systemMapChart = null;
      return;
    }
    el.setAttribute("aria-label", systemMapSummaryText(map));
    if (typeof echarts === "undefined") {
      summary.innerHTML = systemMapSummaryHtml(map);
      summary.classList.add("is-shown");
      return;
    }
    if (!state.systemMapChart) {
      state.systemMapChart = echarts.init(el);
      state.systemMapChart.on("click", (params) => {
        if (params.data?.systemCode) focusExploreOnSystem(params.data.systemCode);
      });
      if (!state.systemMapResizeBound) {
        state.systemMapResizeBound = true;
        window.addEventListener("resize", () => state.systemMapChart?.resize());
      }
    }
    const chart = state.systemMapChart;
    if (!animate || prefersReducedMotion()) {
      chart.setOption(systemMapOption(map, 1), true);
      summary.innerHTML = systemMapSummaryHtml(map);
      summary.classList.add("is-shown");
      return;
    }
    panel.classList.add("is-intro");
    const startedAt = performance.now();
    const frame = (now) => {
      const t = Math.min((now - startedAt) / SYSTEM_MAP_INTRO_MS, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      chart.setOption(systemMapOption(map, eased), true);
      summary.innerHTML = systemMapSummaryHtml(map, eased);
      if (t < 1) requestAnimationFrame(frame);
      else summary.classList.add("is-shown");
    };
    requestAnimationFrame(frame);
  }

  async function loadBoard({ silent = false } = {}) {
    if (state.boardLoadInFlight) return;
    state.boardLoadInFlight = true;
    if (!silent) {
      document.getElementById("runs-board-loading")?.classList.remove("hidden");
    }
    try {
      const [boardRes, heatmapPayload] = await Promise.all([
        fetch("/api/admin/runs/board"),
        loadHeatmap(),
      ]);
      if (!boardRes.ok) throw new Error("board");
      state.board = await boardRes.json();
      state.todayStart = state.board.today_start || null;
      document.getElementById("runs-board-loading")?.classList.add("hidden");
      document.getElementById("runs-board")?.classList.remove("hidden");
      renderSystemMap(state.board.system_map, { animate: !silent && !state.systemMapShown });
      state.systemMapShown = true;
      renderHeatmapPanel(heatmapPayload);
      updateRunsUpdatedAt(heatmapPayload?.generated_at || state.board.generated_at);
    } finally {
      state.boardLoadInFlight = false;
    }
  }

  async function loadRuns({ reset = true, silent = false } = {}) {
    if (state.runsLoadInFlight) return;
    state.runsLoadInFlight = true;
    const previousCount = state.runs.length;
    if (reset) {
      state.offset = 0;
      if (!silent) state.runs = [];
    }
    let query = buildRunsQuery(state.offset);
    if (silent && reset && previousCount > 0) {
      const params = new URLSearchParams(query);
      params.set("limit", String(Math.max(previousCount, PAGE_SIZE)));
      params.set("offset", "0");
      query = params.toString();
    }
    try {
      const res = await fetch(`/api/admin/runs?${query}`);
      if (!res.ok) {
        if (!silent) {
          cardGrid.innerHTML =
            '<p class="adm-run-card__empty text-red-500">목록을 불러오지 못했습니다.</p>';
        }
        return;
      }
      const data = await res.json();
      const items = data.items || [];
      state.total = data.total ?? items.length;
      if (reset) state.runs = items;
      else state.runs = state.runs.concat(items);
      state.offset = state.runs.length;
      renderRunsList();
      updatePageMeta();
      if (!silent) renderActiveFilters();
      syncUrl();
    } finally {
      state.runsLoadInFlight = false;
    }
  }

  async function softRefresh() {
    if (document.hidden) return;
    await Promise.all([loadBoard({ silent: true }), loadRuns({ reset: true, silent: true })]);
  }

  function crossLinksHtml(run) {
    const links = [
      `<a href="/runs/${encodeURIComponent(run.run_id)}" class="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-700">Run 상세</a>`,
    ];
    if (run.suite_id) {
      links.push(
        `<a href="/suites/${encodeURIComponent(run.suite_id)}" class="rounded-lg border border-violet-200 px-3 py-2 text-xs font-semibold text-violet-700 hover:bg-violet-50">Suite</a>`
      );
    }
    if (run.schedule_id) {
      links.push(
        `<a href="/schedules?open=${encodeURIComponent(run.schedule_id)}" class="rounded-lg border border-sky-200 px-3 py-2 text-xs font-semibold text-sky-700 hover:bg-sky-50">예약</a>`
      );
    }
    if (["ANOMALY", "ERROR", "FAILED"].includes(run.status)) {
      links.push(
        `<a href="/anomalies?system=${encodeURIComponent(run.system_code)}" class="rounded-lg border border-amber-200 px-3 py-2 text-xs font-semibold text-amber-800 hover:bg-amber-50">이상징후 인박스</a>`
      );
    }
    return links.join("");
  }

  function renderModuleTimeline(modules) {
    if (!modules.length) {
      return '<p class="text-xs text-gray-400">모듈 이력 없음</p>';
    }
    return `<div class="adm-module-timeline">${modules
      .map((mod) => {
        const cls = MODULE_STATUS_CLASS[mod.status] || "";
        return `<div class="adm-module-timeline__item ${cls}">
          <p class="text-xs font-semibold text-gray-800">${escapeHtml(mod.name || mod.module_id)}</p>
          <p class="text-[10px] text-gray-500">${escapeHtml(mod.status)}</p>
        </div>`;
      })
      .join("")}</div>`;
  }

  async function fetchRunDetail(runId) {
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
      if (res.ok) return await res.json();
    } catch (_) {
      return null;
    }
    return null;
  }

  async function resolveRun(runId) {
    const fromList = state.runs.find((item) => item.run_id === runId);
    if (fromList) return fromList;
    return fetchRunDetail(runId);
  }

  async function openDrawerForRunId(runId) {
    const run = await resolveRun(runId);
    if (run) await openDrawer(run);
  }

  async function openDrawer(run) {
    state.drawerRun = run;
    const pct = run.module_total > 0 ? Math.round((run.module_passed / run.module_total) * 100) : 0;
    const canDelete = !["RUNNING", "PENDING", "WAITING_INPUT"].includes(run.status);
    document.getElementById("runs-drawer-actions")?.classList.toggle("hidden", !canDelete);
    document.getElementById("runs-drawer-menu-dropdown")?.classList.add("hidden");

    const body = document.getElementById("runs-drawer-body");
    body.innerHTML = '<p class="text-sm text-gray-400">모듈 이력 불러오는 중…</p>';
    document.getElementById("runs-drawer-backdrop").classList.add("is-open");
    document.getElementById("runs-drawer").classList.add("is-open");

    let modules = [];
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(run.run_id)}/nodes`);
      modules = res.ok ? await res.json() : [];
    } catch (_) {
      modules = [];
    }

    body.innerHTML = `
      <div class="space-y-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wider text-gray-400">시스템</p>
          <p class="mt-1 text-sm font-bold text-gray-900">${escapeHtml(run.system_name)}</p>
          <p class="font-mono text-xs text-gray-400">${escapeHtml(run.run_id)}</p>
        </div>
        <div class="adm-progress"><div class="adm-progress__fill" style="width:${pct}%"></div></div>
        <p class="text-xs text-gray-500">${escapeHtml(moduleSummary(run))}</p>
        ${comparisonDrawerHtml(run)}
        <dl class="grid grid-cols-2 gap-3 text-xs">
          <div><dt class="text-gray-400">상태</dt><dd class="font-semibold text-gray-800">${escapeHtml(run.status_label)}</dd></div>
          <div><dt class="text-gray-400">실행자</dt><dd class="font-semibold text-gray-800">${escapeHtml(run.created_by_user_name || "(시스템)")}</dd></div>
          <div><dt class="text-gray-400">트리거</dt><dd class="font-semibold text-gray-800">${escapeHtml(triggerLabel(run.triggered_by))}</dd></div>
          <div><dt class="text-gray-400">소요</dt><dd class="font-semibold text-gray-800">${escapeHtml(formatDuration(run.started_at, run.ended_at))}</dd></div>
        </dl>
        <div>
          <p class="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">모듈 타임라인</p>
          ${renderModuleTimeline(modules)}
        </div>
        <div class="flex flex-wrap gap-2 pt-2">${crossLinksHtml(run)}</div>
      </div>`;
  }

  function closeDrawer() {
    document.getElementById("runs-drawer-backdrop").classList.remove("is-open");
    document.getElementById("runs-drawer").classList.remove("is-open");
    state.drawerRun = null;
  }

  function openDeleteModal(runId) {
    state.pendingDeleteId = runId;
    document.getElementById("runs-delete-run-id").textContent = runId;
    document.getElementById("runs-delete-modal").classList.add("is-open");
  }

  function closeDeleteModal() {
    state.pendingDeleteId = null;
    document.getElementById("runs-delete-modal").classList.remove("is-open");
  }

  async function confirmDelete() {
    const runId = state.pendingDeleteId;
    if (!runId) return;
    const response = await fetch(`/api/admin/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
    closeDeleteModal();
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      showToast(body.detail || "삭제에 실패했습니다.", "error");
      return;
    }
    showToast("Run이 삭제되었습니다.", "success");
    await Promise.all([loadBoard(), loadRuns({ reset: true })]);
  }

  function exportCsv() {
    const qs = buildRunsQuery(0, { forExport: true });
    window.location.href = `/api/admin/runs/export.csv?${qs}`;
  }

  async function populateSelects() {
    const [usersRes, systemsRes] = await Promise.all([
      fetch("/api/admin/users"),
      fetch("/api/admin/systems"),
    ]);
    state.users = usersRes.ok ? await usersRes.json() : [];
    state.systems = systemsRes.ok ? await systemsRes.json() : [];

    renderSystemFilterOptions();

    const userSelect = document.getElementById("filter-user");
    if (userSelect.options.length <= 1) {
      state.users.forEach((user) => {
        const option = document.createElement("option");
        option.value = user.user_id || user.id;
        option.textContent = user.name || user.email || user.user_id || user.id;
        userSelect.appendChild(option);
      });
    }
  }

  function bindEvents() {
    document.getElementById("filter-period").addEventListener("change", () => {
      if (document.getElementById("filter-period").value) clearCustomDateFilters();
    });
    document.getElementById("filter-from-dt").addEventListener("change", () => {
      setSegmentValue("filter-period-segment", "filter-period", "periodValue", "");
      state.fromFilter = "";
      state.toFilter = "";
      loadRuns({ reset: true });
    });
    document.getElementById("filter-to-dt").addEventListener("change", () => {
      setSegmentValue("filter-period-segment", "filter-period", "periodValue", "");
      state.fromFilter = "";
      state.toFilter = "";
      loadRuns({ reset: true });
    });
    document.getElementById("filter-user").addEventListener("change", () => loadRuns({ reset: true }));
    document.getElementById("filter-run-id").addEventListener("input", scheduleFilterLoad);
    document.getElementById("filter-user-name").addEventListener("input", scheduleFilterLoad);
    document.getElementById("btn-toggle-advanced").addEventListener("click", () => {
      const panel = document.getElementById("runs-advanced-filters");
      const btn = document.getElementById("btn-toggle-advanced");
      const open = panel.classList.toggle("hidden");
      btn.classList.toggle("is-open", !open);
      btn.setAttribute("aria-expanded", open ? "false" : "true");
    });
    document.querySelectorAll("[data-filter-popover]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleFilterPopover(btn.dataset.filterPopover);
      });
    });
    document.getElementById("filter-system-options")?.addEventListener("change", (event) => {
      const checkbox = event.target.closest(".adm-filter-option[data-group='system']");
      if (!checkbox) return;
      setMultiSelectValues("filter-system", getFilterGroupValues("system"));
      updateFilterTriggerLabel("system");
      loadRuns({ reset: true });
    });
    document.getElementById("filter-popover-status")?.addEventListener("change", (event) => {
      const checkbox = event.target.closest(".adm-filter-option[data-group='status']");
      if (!checkbox) return;
      setMultiSelectValues("filter-status", getFilterGroupValues("status"));
      updateFilterTriggerLabel("status");
      loadRuns({ reset: true });
    });
    document.getElementById("filter-trigger-segment").addEventListener("click", (event) => {
      const btn = event.target.closest("[data-trigger-value]");
      if (!btn) return;
      setSegmentValue("filter-trigger-segment", "filter-trigger", "triggerValue", btn.dataset.triggerValue);
      loadRuns({ reset: true });
    });
    document.getElementById("filter-period-segment").addEventListener("click", (event) => {
      const btn = event.target.closest("[data-period-value]");
      if (!btn) return;
      setSegmentValue("filter-period-segment", "filter-period", "periodValue", btn.dataset.periodValue);
      if (btn.dataset.periodValue) clearCustomDateFilters();
      loadRuns({ reset: true });
    });
    document.getElementById("btn-reset").addEventListener("click", () => {
      state.preset = "all";
      clearCustomDateFilters();
      setFilterGroupValues("system", []);
      setFilterGroupValues("status", []);
      setSegmentValue("filter-trigger-segment", "filter-trigger", "triggerValue", "");
      setSegmentValue("filter-period-segment", "filter-period", "periodValue", "");
      document.getElementById("filter-user").value = "";
      document.getElementById("filter-user-name").value = "";
      document.getElementById("filter-run-id").value = "";
      document.getElementById("runs-advanced-filters").classList.add("hidden");
      renderPresets();
      loadRuns({ reset: true });
    });
    document.getElementById("btn-load-more").addEventListener("click", () => loadRuns({ reset: false }));
    document.getElementById("btn-export-csv").addEventListener("click", exportCsv);
    document.getElementById("btn-save-view").addEventListener("click", saveCurrentView);
    document.getElementById("runs-presets").addEventListener("click", (event) => {
      const btn = event.target.closest("[data-preset]");
      if (!btn) return;
      if (btn.dataset.preset === "attention") {
        setFilterGroupValues("status", []);
        setSegmentValue("filter-period-segment", "filter-period", "periodValue", "7d");
        setSegmentValue("filter-trigger-segment", "filter-trigger", "triggerValue", "");
        clearCustomDateFilters();
      } else {
        applyPreset(btn.dataset.preset);
      }
      state.preset = btn.dataset.preset;
      renderPresets();
      loadRuns({ reset: true });
    });
    document.getElementById("runs-saved-views").addEventListener("click", (event) => {
      const deleteBtn = event.target.closest("[data-delete-view]");
      if (deleteBtn) {
        event.stopPropagation();
        state.savedViews = state.savedViews.filter((view) => view.id !== deleteBtn.dataset.deleteView);
        persistSavedViews();
        renderSavedViews();
        return;
      }
      const viewBtn = event.target.closest("[data-saved-view]");
      if (viewBtn) applySavedView(viewBtn.dataset.savedView);
    });
    document.getElementById("runs-active-filters").addEventListener("click", (event) => {
      const btn = event.target.closest("[data-clear]");
      if (!btn) return;
      const key = btn.dataset.clear;
      if (key === "preset") state.preset = "all";
      if (key === "system") setFilterGroupValues("system", []);
      if (key === "status") setFilterGroupValues("status", []);
      if (key === "trigger") setSegmentValue("filter-trigger-segment", "filter-trigger", "triggerValue", "");
      if (key === "period") {
        setSegmentValue("filter-period-segment", "filter-period", "periodValue", "");
        clearCustomDateFilters();
      }
      if (key === "from") {
        state.fromFilter = "";
        document.getElementById("filter-from-dt").value = "";
      }
      if (key === "to") {
        state.toFilter = "";
        document.getElementById("filter-to-dt").value = "";
      }
      if (key === "user") document.getElementById("filter-user").value = "";
      if (key === "user_name") document.getElementById("filter-user-name").value = "";
      if (key === "run_id") document.getElementById("filter-run-id").value = "";
      if (key !== "preset") state.preset = "all";
      renderPresets();
      loadRuns({ reset: true });
    });
    cardGrid.addEventListener("click", (event) => {
      const menuBtn = event.target.closest("[data-row-menu-toggle]");
      if (menuBtn) {
        event.stopPropagation();
        toggleRowMenu(menuBtn.dataset.rowMenuToggle);
        return;
      }
      const actionBtn = event.target.closest("[data-row-action]");
      if (actionBtn) {
        event.stopPropagation();
        closeRowMenus();
        const runId = actionBtn.dataset.runId;
        if (actionBtn.dataset.rowAction === "detail") {
          openDrawerForRunId(runId);
        } else if (actionBtn.dataset.rowAction === "delete") {
          openDeleteModal(runId);
        }
        return;
      }
      if (event.target.closest("[data-row-action-cell]")) return;
      const card = event.target.closest("[data-run-id]");
      if (!card) return;
      closeRowMenus();
      const run = state.runs.find((item) => item.run_id === card.dataset.runId);
      if (run) openDrawer(run);
    });
    document.getElementById("runs-drawer-menu-btn")?.addEventListener("click", (event) => {
      event.stopPropagation();
      document.getElementById("runs-drawer-menu-dropdown")?.classList.toggle("hidden");
    });
    document.getElementById("runs-drawer-delete-btn")?.addEventListener("click", () => {
      if (!state.drawerRun) return;
      document.getElementById("runs-drawer-menu-dropdown")?.classList.add("hidden");
      openDeleteModal(state.drawerRun.run_id);
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".adm-filter-group")) closeFilterPopovers();
      if (!event.target.closest("[data-row-action-cell]")) closeRowMenus();
      const wrap = document.getElementById("runs-drawer-actions");
      if (!wrap || wrap.classList.contains("hidden")) return;
      if (event.target.closest("#runs-drawer-actions")) return;
      document.getElementById("runs-drawer-menu-dropdown")?.classList.add("hidden");
    });
    document.getElementById("runs-drawer-close").addEventListener("click", closeDrawer);
    document.getElementById("runs-drawer-backdrop").addEventListener("click", closeDrawer);
    document.getElementById("runs-delete-cancel").addEventListener("click", closeDeleteModal);
    document.getElementById("runs-delete-confirm").addEventListener("click", confirmDelete);
    document.getElementById("runs-delete-modal").addEventListener("click", (event) => {
      if (event.target.id === "runs-delete-modal") closeDeleteModal();
    });
  }

  async function init() {
    loadSavedViews();
    const restored = restoreFromUrl();
    if (!restored) applyPreset("attention");
    renderSavedViews();
    bindEvents();
    await populateSelects();
    try {
      await loadBoard();
    } catch (_) {
      document.getElementById("runs-board-loading").textContent = "보드를 불러오지 못했습니다.";
    }
    await loadRuns({ reset: true });
    setInterval(softRefresh, REFRESH_MS);
  }

  init();
})();
