// 이상징후 인박스 — /api/anomalies 를 불러와 이상건 리스트를 렌더하고,
// 처리상태(미확인/확인함/처리완료)·담당자·메모 변경을 PATCH 로 저장한다.
// anomalies.html 이 로드된 페이지에서만 동작한다(다른 페이지에서는 no-op).

(() => {
  const root = document.querySelector(".inbox");
  if (!root) return;

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

  const STATE_LABELS = { UNRESOLVED: "미확인", ACKNOWLEDGED: "확인함", RESOLVED: "처리완료" };
  const PILL_CLASS = {
    anomaly: "bg-amber-100 text-amber-700",
    error: "bg-red-100 text-red-700",
    passed: "bg-green-100 text-green-700",
  };

  const state = {
    items: [],
    counts: {},
    assignees: [],
    filterState: "all",
    filterSystem: "all",
    filterKind: "all",
  };

  // ── 유틸 ────────────────────────────────────────────────────────────────
  function relTime(iso) {
    if (!iso) return "";
    const then = new Date(iso).getTime();
    const diff = Date.now() - then;
    const min = Math.floor(diff / 60000);
    if (min < 1) return "방금";
    if (min < 60) return `${min}분 전`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}시간 전`;
    const day = Math.floor(hr / 24);
    if (day < 30) return `${day}일 전`;
    return new Date(iso).toLocaleDateString("ko-KR");
  }

  async function patch(moduleRunId, body) {
    const res = await fetch(`/api/anomalies/${encodeURIComponent(moduleRunId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`PATCH failed: ${res.status}`);
    return res.json();
  }

  // ── 로드 ────────────────────────────────────────────────────────────────
  async function load() {
    $("#inbox-loading")?.classList.remove("hidden");
    $("#inbox-error")?.classList.add("hidden");
    try {
      const [data, assignees] = await Promise.all([
        fetch("/api/anomalies").then((r) => (r.ok ? r.json() : Promise.reject(r))),
        fetch("/api/anomalies/assignees").then((r) => (r.ok ? r.json() : [])),
      ]);
      state.items = data.items || [];
      state.counts = data.counts || {};
      state.assignees = assignees || [];
      populateSystemFilter(data.systems || []);
      render();
    } catch (_) {
      $("#inbox-error")?.classList.remove("hidden");
      $("#inbox-list").innerHTML = "";
    } finally {
      $("#inbox-loading")?.classList.add("hidden");
    }
  }

  function populateSystemFilter(systems) {
    const sel = $("#inbox-filter-system");
    const urlSystem = new URLSearchParams(location.search).get("system");
    const current = urlSystem || sel.value;
    sel.innerHTML = '<option value="all">전체 시스템</option>';
    for (const s of systems) {
      const opt = document.createElement("option");
      opt.value = s.system_code;
      opt.textContent = s.system_name;
      sel.appendChild(opt);
    }
    if (urlSystem && systems.some((s) => s.system_code === urlSystem)) {
      state.filterSystem = urlSystem;
      sel.value = urlSystem;
    } else {
      sel.value = current || "all";
    }
  }

  // ── 필터 적용 ────────────────────────────────────────────────────────────
  function visibleItems() {
    return state.items.filter((it) => {
      if (state.filterState !== "all" && it.handling.state !== state.filterState) return false;
      if (state.filterSystem !== "all" && it.system_code !== state.filterSystem) return false;
      if (state.filterKind !== "all" && it.kind !== state.filterKind) return false;
      return true;
    });
  }

  // ── 렌더 ────────────────────────────────────────────────────────────────
  function renderCounts() {
    $$("[data-count]").forEach((el) => {
      const key = el.dataset.count;
      el.textContent = state.counts[key] ?? 0;
    });
    $$(".inbox-kpi").forEach((btn) => {
      btn.dataset.active = String(btn.dataset.filterState === state.filterState);
    });
    // 사이드바·햄버거 배지 동기화
    window.E2ENavBadges?.setCounts?.({ anomaly: state.counts.unresolved || 0 });
  }

  function render() {
    renderCounts();
    const list = $("#inbox-list");
    list.innerHTML = "";
    const items = visibleItems();
    $("#inbox-visible-count").textContent = items.length
      ? `${items.length}건 표시 중`
      : "";
    $("#inbox-empty").classList.toggle("hidden", items.length > 0);

    const tpl = $("#inbox-card-template");
    items.forEach((it, i) => {
      const node = tpl.content.firstElementChild.cloneNode(true);
      hydrate(node, it);
      list.appendChild(node);
      requestAnimationFrame(() => setTimeout(() => node.classList.add("is-in"), i * 25));
    });
  }

  function hydrate(node, it) {
    node.dataset.state = it.handling.state;

    // 썸네일
    const thumbLink = $('[data-field="thumb-link"]', node);
    const thumb = $('[data-field="thumb"]', node);
    const thumbEmpty = $('[data-field="thumb-empty"]', node);
    if (it.screenshot) {
      thumb.src = it.screenshot;
      thumbLink.href = it.screenshot;
      thumbEmpty.classList.add("hidden");
    } else {
      thumb.classList.add("hidden");
      thumbLink.removeAttribute("href");
    }

    // 상태 pill
    const pill = $('[data-field="status-pill"]', node);
    pill.textContent = it.status_label;
    pill.className = `rounded-full px-2 py-0.5 text-[11px] font-bold ${PILL_CLASS[it.tone] || "bg-gray-100 text-gray-600"}`;

    $('[data-field="system"]', node).textContent = it.system_name;
    $('[data-field="module"]', node).textContent = it.module_name;
    $('[data-field="occurred"]', node).textContent = relTime(it.occurred_at);
    $('[data-field="summary"]', node).textContent =
      it.ai_summary || it.message || "요약 정보 없음";

    const cat = $('[data-field="category"]', node);
    if (it.ai_category) {
      cat.textContent = it.ai_category;
      cat.classList.remove("hidden");
    }
    $('[data-field="run-link"]', node).href = `/runs/${it.run_id}`;
    const url = $('[data-field="url"]', node);
    url.textContent = it.current_url || "";
    url.title = it.current_url || "";

    // 세그먼트 토글
    const seg = $('[data-field="seg"]', node);
    $$(".inbox-seg__btn", seg).forEach((btn) => {
      btn.setAttribute("aria-pressed", String(btn.dataset.seg === it.handling.state));
      btn.addEventListener("click", () => onState(node, it, btn.dataset.seg));
    });

    // 담당자
    const assignee = $('[data-field="assignee"]', node);
    assignee.innerHTML = '<option value="">담당자 미배정</option>';
    for (const u of state.assignees) {
      const opt = document.createElement("option");
      opt.value = u.user_id;
      opt.textContent = u.name;
      assignee.appendChild(opt);
    }
    assignee.value = it.handling.assignee_user_id || "";
    assignee.addEventListener("change", () => onAssignee(node, it, assignee.value));

    // 메모
    const memo = $('[data-field="memo"]', node);
    memo.value = it.handling.memo || "";
    memo.addEventListener("change", () => onMemo(node, it, memo.value));
  }

  // ── 처리 액션(낙관적 업데이트) ─────────────────────────────────────────────
  function recount() {
    state.counts.unresolved = state.items.filter((i) => i.handling.state === "UNRESOLVED").length;
    state.counts.acknowledged = state.items.filter((i) => i.handling.state === "ACKNOWLEDGED").length;
    state.counts.resolved = state.items.filter((i) => i.handling.state === "RESOLVED").length;
    renderCounts();
  }

  function flashSaved(node) {
    const saved = $('[data-field="saved"]', node);
    if (!saved) return;
    saved.classList.remove("hidden");
    setTimeout(() => saved.classList.add("hidden"), 1400);
  }

  async function onState(node, it, next) {
    const prev = it.handling.state;
    if (prev === next) return;
    it.handling.state = next;
    node.dataset.state = next;
    $$(".inbox-seg__btn", node).forEach((btn) =>
      btn.setAttribute("aria-pressed", String(btn.dataset.seg === next)),
    );
    recount();
    // 현재 상태 필터에서 벗어나면 리스트에서 사라지게 재렌더
    if (state.filterState !== "all" && state.filterState !== next) render();
    try {
      await patch(it.module_run_id, { state: next });
      flashSaved(node);
    } catch (_) {
      it.handling.state = prev;
      recount();
      render();
    }
  }

  async function onAssignee(node, it, userId) {
    const prevId = it.handling.assignee_user_id;
    const prevName = it.handling.assignee_name;
    it.handling.assignee_user_id = userId || null;
    it.handling.assignee_name = state.assignees.find((u) => u.user_id === userId)?.name || null;
    try {
      await patch(it.module_run_id, { assignee_user_id: userId });
      flashSaved(node);
    } catch (_) {
      it.handling.assignee_user_id = prevId;
      it.handling.assignee_name = prevName;
      $('[data-field="assignee"]', node).value = prevId || "";
    }
  }

  async function onMemo(node, it, memo) {
    const prev = it.handling.memo;
    if (prev === memo) return;
    it.handling.memo = memo;
    try {
      await patch(it.module_run_id, { memo });
      flashSaved(node);
    } catch (_) {
      it.handling.memo = prev;
      $('[data-field="memo"]', node).value = prev || "";
    }
  }

  // ── 필터 이벤트 ──────────────────────────────────────────────────────────
  $$(".inbox-kpi").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.filterState = btn.dataset.filterState;
      render();
    });
  });
  $("#inbox-filter-system").addEventListener("change", (e) => {
    state.filterSystem = e.target.value;
    render();
  });
  $("#inbox-filter-kind").addEventListener("change", (e) => {
    state.filterKind = e.target.value;
    render();
  });
  $("#inbox-refresh").addEventListener("click", load);

  load();
})();
