// 프리셋 관리 — 저장된 인증 프리셋 조회·수정·삭제 (presets.html 전용)
(function () {
  const root = document.getElementById("presets-root");
  if (!root) return;

  const systemsEl = document.getElementById("presets-systems-data");
  const SYSTEMS = systemsEl ? JSON.parse(systemsEl.textContent || "{}") : {};

  const AUTH_METHOD_LABELS = {
    phone: "휴대폰인증",
    kakao: "카카오인증",
    finance_certificate: "금융인증서",
    public_certificate: "공동인증서",
  };

  const state = {
    presets: [],
    filter: "all",
    editing: null,
    loading: false,
  };

  const $ = (selector, parent = root) => parent.querySelector(selector);
  const $$ = (selector, parent = root) => Array.from(parent.querySelectorAll(selector));

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function authMethodLabel(method) {
    return AUTH_METHOD_LABELS[method] ?? (method || "인증");
  }

  function presetSummary(preset) {
    const parts = [authMethodLabel(preset.auth_method)];
    const data = preset.input_data ?? {};
    if (data.name) parts.push(data.name);
    if (data.phone_number) {
      const phone = String(data.phone_number);
      parts.push(phone.length > 4 ? `${phone.slice(0, 3)}****${phone.slice(-4)}` : phone);
    }
    return parts.join(" · ");
  }

  function formatDate(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString("ko-KR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function toast(message, tone = "error") {
    const container = document.getElementById("toast-container");
    if (!container) {
      window.alert(message);
      return;
    }
    const node = document.createElement("div");
    node.className = `pointer-events-auto rounded-xl px-4 py-2.5 text-sm font-semibold shadow-lg ${
      tone === "success" ? "bg-emerald-600 text-white" : "bg-red-600 text-white"
    }`;
    node.textContent = message;
    container.appendChild(node);
    window.setTimeout(() => node.remove(), 4200);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      let detail = "";
      try {
        const body = await response.json();
        detail = body.detail || body.message || "";
      } catch {
        detail = await response.text();
      }
      throw new Error(detail || `요청 실패 (${response.status})`);
    }
    if (response.status === 204) return null;
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  }

  function filteredPresets() {
    if (state.filter === "all") return state.presets;
    return state.presets.filter((preset) => preset.system_code === state.filter);
  }

  function moduleLabel(systemCode, moduleId) {
    const system = SYSTEMS[systemCode];
    const module = (system?.modules || []).find((item) => item.module_id === moduleId);
    return module?.name || moduleId;
  }

  function renderFilters() {
    const wrap = $("#prset-filter");
    if (!wrap) return;
    const systems = Object.values(SYSTEMS).sort(
      (left, right) => (left.display_order ?? 0) - (right.display_order ?? 0) || left.name.localeCompare(right.name, "ko"),
    );
    const buttons = [
      { code: "all", label: "전체" },
      ...systems.map((system) => ({ code: system.system_code, label: system.name })),
    ];
    wrap.innerHTML = buttons
      .map(
        (item) => `<button type="button" class="prset-filter__btn" data-filter="${esc(item.code)}" aria-pressed="${state.filter === item.code ? "true" : "false"}">${esc(item.label)}</button>`,
      )
      .join("");
    for (const button of $$("[data-filter]", wrap)) {
      button.addEventListener("click", () => {
        state.filter = button.dataset.filter;
        renderFilters();
        renderList();
      });
    }
  }

  function renderList() {
    const list = $("#prset-list");
    const empty = $("#prset-empty");
    const count = $('[data-role="preset-count"]');
    const items = filteredPresets();
    if (count) count.textContent = String(items.length);

    if (!list || !empty) return;
    list.innerHTML = "";

    if (state.loading) {
      empty.classList.add("hidden");
      list.innerHTML = '<p class="rounded-2xl border border-gray-100 bg-white px-5 py-8 text-center text-sm text-gray-500 shadow-sm">프리셋을 불러오는 중…</p>';
      return;
    }

    if (items.length === 0) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");

    for (const preset of items) {
      const card = document.createElement("article");
      card.className =
        "rounded-2xl border border-gray-100 bg-white p-4 shadow-sm transition hover:border-indigo-100 hover:shadow-md";
      const moduleIds = preset.selected_module_ids ?? [];
      const moduleText =
        moduleIds.length > 0
          ? moduleIds.map((id) => moduleLabel(preset.system_code, id)).join(", ")
          : "전체 모듈";
      card.innerHTML = `
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="inline-flex shrink-0 items-center rounded-md bg-indigo-50 px-2 py-0.5 font-mono text-[10px] font-bold text-indigo-700 ring-1 ring-inset ring-indigo-200">${esc(preset.system_code.toUpperCase())}</span>
              <h3 class="truncate text-sm font-bold text-gray-900">${esc(preset.name)}</h3>
            </div>
            <p class="mt-1 text-xs text-gray-500">${esc(presetSummary(preset))}</p>
            <p class="mt-1 text-[11px] text-gray-400">모듈: ${esc(moduleText)}</p>
            <p class="mt-1 text-[11px] text-gray-400">수정: ${esc(formatDate(preset.updated_at))}</p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <button type="button" data-role="edit" class="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-700 transition hover:bg-gray-50">수정</button>
            <button type="button" data-role="delete" class="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-600 transition hover:bg-red-50">삭제</button>
          </div>
        </div>`;
      $('[data-role="edit"]', card).addEventListener("click", () => openDrawer(preset));
      $('[data-role="delete"]', card).addEventListener("click", () => deletePreset(preset));
      list.appendChild(card);
    }
  }

  function closeDrawer() {
    root.classList.remove("is-drawer-open");
    state.editing = null;
    const body = $("#prset-drawer-body");
    if (body) body.innerHTML = "";
  }

  function openDrawer(preset) {
    state.editing = preset;
    root.classList.add("is-drawer-open");
    $("#prset-drawer-system").textContent = preset.system_code.toUpperCase();
    $("#prset-drawer-title").textContent = preset.name;
    $("#prset-drawer-sub").textContent = `${preset.system_name} · 생성 ${formatDate(preset.created_at)}`;

    const body = $("#prset-drawer-body");
    if (!body) return;
    body.innerHTML = "";

    const nameBlock = document.createElement("label");
    nameBlock.className = "block";
    nameBlock.innerHTML = `<span class="text-xs font-semibold text-gray-700">프리셋 이름</span>
      <input type="text" data-edit="name" maxlength="40" class="prset-field mt-1.5" value="${esc(preset.name)}">`;
    body.appendChild(nameBlock);

    const authBlock = buildAuthFields(preset);
    body.appendChild(authBlock);

    const moduleBlock = buildModuleFields(preset);
    body.appendChild(moduleBlock);

    const footer = document.createElement("div");
    footer.className = "flex flex-wrap items-center gap-2 border-t border-gray-100 pt-4";
    footer.innerHTML = `
      <button type="button" data-role="drawer-delete" class="rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-600 transition hover:bg-red-50">삭제</button>
      <button type="button" data-role="drawer-cancel" class="ml-auto rounded-lg border border-gray-200 px-3 py-2 text-xs font-semibold text-gray-600 transition hover:bg-gray-50">취소</button>
      <button type="button" data-role="drawer-save" class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-bold text-white shadow-sm transition hover:bg-indigo-700 disabled:opacity-50">저장</button>`;
    $('[data-role="drawer-delete"]', footer).addEventListener("click", () => deletePreset(preset, { closeOnSuccess: true }));
    $('[data-role="drawer-cancel"]', footer).addEventListener("click", closeDrawer);
    $('[data-role="drawer-save"]', footer).addEventListener("click", () => savePreset(preset, body, footer));
    body.appendChild(footer);
  }

  function buildAuthFields(preset) {
    const wrap = document.createElement("div");
    const system = SYSTEMS[preset.system_code];
    const fields = (system?.run_form || []).filter((field) => field.key !== "browser_mode");
    wrap.innerHTML = `<span class="text-xs font-semibold text-gray-700">인증 정보</span>
      <p class="mt-0.5 text-[11px] text-gray-400">저장된 값이 미리 채워져 있습니다. 바꿀 항목만 수정하세요.</p>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2" data-role="auth-fields"></div>`;
    const list = $('[data-role="auth-fields"]', wrap);
    if (!fields.length) {
      list.innerHTML = '<p class="col-span-2 text-[11px] text-gray-400">이 시스템은 수정 가능한 입력값이 없습니다.</p>';
      return wrap;
    }

    const data = preset.input_data ?? {};
    const supported = new Set(system?.supported_auth_methods || []);

    const applyVisibility = () => {
      const auth = $('select[data-auth-key="auth_method"]', list)?.value || data.auth_method || "";
      for (const node of $$("[data-show-when]", list)) {
        const allowed = JSON.parse(node.dataset.showWhen);
        node.classList.toggle("hidden", allowed.length > 0 && !allowed.includes(auth));
      }
    };

    for (const field of fields) {
      const holder = document.createElement("label");
      holder.className = "block";
      const showWhen = field.show_when?.auth_method;
      holder.dataset.showWhen = JSON.stringify(
        showWhen ? (Array.isArray(showWhen) ? showWhen : [showWhen]) : [],
      );
      const value = data[field.key] ?? field.default ?? "";
      if (field.type === "select") {
        const options = (field.options || [])
          .map((option) => {
            const unsupported =
              field.key === "auth_method" && supported.size > 0 && !supported.has(option.value);
            const selected = String(option.value) === String(value) ? "selected" : "";
            const suffix = unsupported ? " (준비 중)" : "";
            const disabled = unsupported ? "disabled" : "";
            return `<option value="${esc(option.value)}" ${selected} ${disabled}>${esc(option.label)}${suffix}</option>`;
          })
          .join("");
        holder.innerHTML = `<span class="text-[11px] font-semibold text-gray-500">${esc(field.label)}</span>
          <select data-auth-key="${esc(field.key)}" class="prset-field mt-1 !py-1.5 !text-xs">${options}</select>`;
      } else {
        holder.innerHTML = `<span class="text-[11px] font-semibold text-gray-500">${esc(field.label)}</span>
          <input type="${field.type === "password" ? "password" : "text"}" data-auth-key="${esc(field.key)}"
                 value="${esc(value)}" placeholder="${esc(field.placeholder || "")}" class="prset-field mt-1 !py-1.5 !text-xs">`;
      }
      list.appendChild(holder);
    }
    $('select[data-auth-key="auth_method"]', list)?.addEventListener("change", applyVisibility);
    applyVisibility();
    return wrap;
  }

  function buildModuleFields(preset) {
    const wrap = document.createElement("div");
    const system = SYSTEMS[preset.system_code];
    const modules = system?.modules || [];
    const selected = new Set(
      preset.selected_module_ids?.length
        ? preset.selected_module_ids
        : modules.map((module) => module.module_id),
    );
    wrap.innerHTML = `<span class="text-xs font-semibold text-gray-700">실행 모듈</span>
      <div class="mt-2 grid grid-cols-1 gap-1.5 sm:grid-cols-2" data-role="module-list"></div>`;
    const list = $('[data-role="module-list"]', wrap);
    if (!modules.length) {
      list.innerHTML = '<p class="text-[11px] text-gray-400">모듈 정보를 불러올 수 없습니다.</p>';
      return wrap;
    }
    for (const module of modules) {
      const label = document.createElement("label");
      label.className =
        "flex items-center gap-2 rounded-lg border border-gray-100 bg-gray-50/60 px-2.5 py-1.5 text-xs font-medium text-gray-700";
      label.innerHTML = `<input type="checkbox" data-module-id="${esc(module.module_id)}" ${
        selected.has(module.module_id) ? "checked" : ""
      } class="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600">
        <span class="truncate" title="${esc(module.name)}">${esc(module.name)}</span>`;
      list.appendChild(label);
    }
    return wrap;
  }

  function collectDrawerPayload(preset, section) {
    const payload = {};
    const name = ($('[data-edit="name"]', section)?.value || "").trim();
    if (!name) throw new Error("프리셋 이름을 입력해야 합니다.");
    if (name !== preset.name) payload.name = name;

    const inputData = {};
    for (const field of $$("[data-auth-key]", section)) {
      if (field.closest(".hidden")) continue;
      const value = (field.value || "").trim();
      if (!value) continue;
      inputData[field.dataset.authKey] = value;
    }
    const original = preset.input_data ?? {};
    const merged = { ...original, ...inputData };
    const changedInput = Object.keys(merged).some((key) => String(merged[key] ?? "") !== String(original[key] ?? ""));
    if (changedInput) payload.input_data = merged;

    const moduleBoxes = $$("[data-module-id]", section);
    if (moduleBoxes.length) {
      const chosen = moduleBoxes.filter((box) => box.checked).map((box) => box.dataset.moduleId);
      if (!chosen.length) throw new Error("모듈을 1개 이상 선택해 주세요.");
      const originalModules =
        preset.selected_module_ids?.length
          ? preset.selected_module_ids
          : moduleBoxes.map((box) => box.dataset.moduleId);
      if (JSON.stringify(chosen) !== JSON.stringify(originalModules)) {
        payload.selected_module_ids = chosen;
      }
    }

    return payload;
  }

  async function savePreset(preset, section, footer) {
    const saveButton = $('[data-role="drawer-save"]', footer);
    try {
      const payload = collectDrawerPayload(preset, section);
      if (!Object.keys(payload).length) {
        toast("변경된 내용이 없습니다.", "success");
        return;
      }
      saveButton.disabled = true;
      const updated = await api(`/api/presets/${preset.preset_id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      state.presets = state.presets.map((item) =>
        item.preset_id === updated.preset_id ? updated : item,
      );
      renderList();
      toast("프리셋을 수정했습니다.", "success");
      openDrawer(updated);
    } catch (error) {
      toast(error.message);
    } finally {
      if (saveButton) saveButton.disabled = false;
    }
  }

  async function deletePreset(preset, options = {}) {
    if (!window.confirm(`‘${preset.name}’ 프리셋을 삭제할까요?`)) return;
    try {
      await api(`/api/presets/${preset.preset_id}`, { method: "DELETE" });
      state.presets = state.presets.filter((item) => item.preset_id !== preset.preset_id);
      renderList();
      toast("프리셋을 삭제했습니다.", "success");
      if (options.closeOnSuccess) closeDrawer();
    } catch (error) {
      toast(error.message);
    }
  }

  async function loadPresets() {
    state.loading = true;
    renderList();
    try {
      state.presets = await api("/api/presets");
    } catch (error) {
      state.presets = [];
      toast(error.message);
    } finally {
      state.loading = false;
      renderList();
    }
  }

  function bindEvents() {
    $("#prset-refresh")?.addEventListener("click", () => loadPresets());
    $("#prset-drawer-close")?.addEventListener("click", closeDrawer);
    $("#prset-drawer-backdrop")?.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && root.classList.contains("is-drawer-open")) {
        closeDrawer();
      }
    });
  }

  function reveal() {
    for (const node of $$(".prset-reveal", root)) {
      node.classList.add("is-in");
    }
  }

  renderFilters();
  bindEvents();
  reveal();
  loadPresets();
})();
