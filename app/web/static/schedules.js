// 예약 점검 관리 센터 — 관제 보드(/api/schedules/board) + 시간표 캘린더(/api/schedules/calendar)
// + 예약 상세 드로어(이력 스트립 /api/schedules/{id}/history, in-place 수정 PUT, 일시 중지,
// 복제, 변경 이력)를 렌더링한다. schedules.html 이 로드된 페이지에서만 동작한다.

(() => {
  const root = document.querySelector(".schedc");
  if (!root) return;

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

  const SYSTEMS = (() => {
    try {
      return JSON.parse($("#schedc-systems-data")?.textContent || "{}");
    } catch (_) {
      return {};
    }
  })();

  const STATUS_LABELS = {
    PASSED: "정상",
    ANOMALY: "이상징후",
    FAILED: "이상징후",
    ERROR: "점검실패",
    CANCELLED: "취소됨",
    WAITING_INPUT: "OTP 대기",
    RUNNING: "실행 중",
    PENDING: "대기 중",
  };
  const BADGE_CLASS = {
    PASSED: "bg-green-100 text-green-700",
    ANOMALY: "bg-amber-100 text-amber-700",
    FAILED: "bg-amber-100 text-amber-700",
    ERROR: "bg-red-100 text-red-700",
    CANCELLED: "bg-gray-100 text-gray-500",
    WAITING_INPUT: "bg-red-100 text-red-700",
    RUNNING: "bg-indigo-100 text-indigo-700",
    PENDING: "bg-indigo-50 text-indigo-500",
  };
  const ISSUE_META = {
    stuck: { icon: "🔴", label: "OTP에서 멈춤", cta: "OTP 입력하러 가기" },
    failing: { icon: "🟠", label: "연속 실패 중", cta: "최근 결과 보기" },
    missed: { icon: "🟡", label: "실행 누락/건너뜀", cta: "상세 보기" },
    stale: { icon: "⚪", label: "꺼진 지 오래", cta: "예약 켜기" },
  };
  const CHANGE_ACTION_LABELS = {
    created: "등록",
    updated: "수정",
    enabled: "켬",
    disabled: "끔",
    paused: "일시 중지",
    pause_cleared: "재개",
    auto_resumed: "자동 재개",
    duplicated: "복제 생성",
  };
  const DOW_LABELS = ["일", "월", "화", "수", "목", "금", "토"];

  const state = {
    view: "list",
    board: null,
    schedules: [],
    search: "",
    filterKind: "all",
    filterState: "all",
    weekOffset: 0,
    calendar: null,
    drawerId: null,
    drawerDetail: null,
    editState: null,
  };

  // ── 공통 유틸 ───────────────────────────────────────────────────────────
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
    ));

  const toast = (message, tone = "error") => {
    if (typeof showToast === "function") showToast(message, tone);
  };

  function relTime(iso) {
    if (!iso) return "";
    const diff = Date.now() - new Date(iso).getTime();
    const min = Math.floor(diff / 60000);
    if (min < 1) return "방금";
    if (min < 60) return `${min}분 전`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}시간 전`;
    const day = Math.floor(hr / 24);
    if (day < 30) return `${day}일 전`;
    return new Date(iso).toLocaleDateString("ko-KR");
  }

  function absTime(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleString("ko-KR", {
      month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
    });
  }

  // "T-2h 14m" 카운트다운 (기획안 A)
  function countdown(iso) {
    if (!iso) return null;
    let sec = Math.floor((new Date(iso).getTime() - Date.now()) / 1000);
    if (sec <= 0) return "곧 실행";
    const d = Math.floor(sec / 86400); sec %= 86400;
    const h = Math.floor(sec / 3600); sec %= 3600;
    const m = Math.floor(sec / 60);
    if (d > 0) return `T-${d}d ${h}h`;
    if (h > 0) return `T-${h}h ${m}m`;
    if (m > 0) return `T-${m}m`;
    return "1분 이내";
  }

  function formatDuration(ms) {
    if (ms == null) return "–";
    const sec = Math.round(ms / 1000);
    if (sec < 60) return `${sec}초`;
    const min = Math.floor(sec / 60);
    return `${min}분 ${sec % 60}초`;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      ...options,
    });
    if (!response.ok) {
      let detail = `요청 실패 (${response.status})`;
      try {
        const body = await response.json();
        if (body?.detail) detail = typeof body.detail === "string" ? body.detail : detail;
      } catch (_) { /* noop */ }
      throw new Error(detail);
    }
    return response.json();
  }

  const scheduleLink = (schedule) => {
    if (schedule.schedule_kind === "suite") {
      return schedule.last_suite_id ? `/suites/${schedule.last_suite_id}` : null;
    }
    return schedule.last_run_id ? `/runs/${schedule.last_run_id}` : null;
  };

  const lastStatus = (schedule) =>
    schedule.schedule_kind === "suite" ? schedule.last_suite_status : schedule.last_run_status;

  // ── 보드 로드/렌더 ──────────────────────────────────────────────────────
  async function loadBoard({ silent = false } = {}) {
    if (!silent) {
      $("#schedc-loading").classList.remove("hidden");
      $("#schedc-error").classList.add("hidden");
    }
    try {
      const board = await api("/api/schedules/board");
      state.board = board;
      state.schedules = board.schedules || [];
      $("#schedc-tz").textContent = board.timezone ? `타임존 ${board.timezone}` : "";
      renderKpi();
      renderAttention();
      renderTable();
      $("#schedc-loading").classList.add("hidden");
    } catch (error) {
      $("#schedc-loading").classList.add("hidden");
      if (!silent) $("#schedc-error").classList.remove("hidden");
    }
  }

  function renderKpi() {
    const kpi = state.board?.kpi || {};
    for (const key of ["total", "active", "today_planned", "attention"]) {
      const node = $(`[data-kpi="${key}"]`, root);
      if (node) node.textContent = kpi[key] ?? "–";
    }
  }

  function issueDescription(schedule, issue) {
    switch (issue.type) {
      case "stuck":
        return "무인 실행이 OTP 입력을 기다리며 멈춰 있습니다.";
      case "failing":
        return `최근 실행이 연달아 ${issue.consecutive_failures}회 실패했습니다.`;
      case "missed":
        return `직전 실행이 끝나지 않아 주기를 건너뛰었습니다 (${relTime(issue.skipped_at)}).`;
      case "stale":
        return `꺼진 상태로 ${issue.disabled_days}일이 지났습니다. 조용히 죽은 예약일 수 있어요.`;
      default:
        return "";
    }
  }

  function renderAttention() {
    const section = $("#schedc-attention");
    const list = $("#schedc-attention-list");
    const items = state.board?.attention || [];
    list.innerHTML = "";
    if (!items.length) {
      section.classList.add("hidden");
      return;
    }
    section.classList.remove("hidden");
    for (const schedule of items) {
      for (const issue of schedule.issues || []) {
        const meta = ISSUE_META[issue.type];
        if (!meta) continue;
        const card = document.createElement("article");
        card.className =
          "schedc-issue-card schedc-reveal flex items-center gap-3 rounded-xl border border-gray-100 bg-white p-3 shadow-sm";
        card.dataset.issue = issue.type;
        card.innerHTML = `
          <span class="text-base leading-none">${meta.icon}</span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-x-2">
              <span class="text-[11px] font-bold text-gray-400">${meta.label}</span>
              <button type="button" data-open="${esc(schedule.schedule_id)}" class="truncate text-sm font-bold text-gray-900 hover:text-indigo-600">${esc(schedule.name || schedule.system_name)}</button>
            </div>
            <p class="mt-0.5 truncate text-xs text-gray-500">${esc(issueDescription(schedule, issue))}</p>
          </div>
          <button type="button" data-issue-cta class="shrink-0 rounded-lg bg-gray-900 px-2.5 py-1.5 text-[11px] font-bold text-white transition hover:bg-gray-700">${meta.cta}</button>`;
        $("[data-open]", card).addEventListener("click", () => openDrawer(schedule.schedule_id));
        $("[data-issue-cta]", card).addEventListener("click", async () => {
          if (issue.type === "stuck" || issue.type === "failing") {
            const link = scheduleLink(schedule);
            if (link) { window.location.href = link; return; }
            openDrawer(schedule.schedule_id);
          } else if (issue.type === "missed") {
            openDrawer(schedule.schedule_id);
          } else if (issue.type === "stale") {
            await toggleSchedule(schedule.schedule_id);
          }
        });
        list.appendChild(card);
        requestAnimationFrame(() => card.classList.add("is-in"));
      }
    }
  }

  // ── 목록 뷰 ─────────────────────────────────────────────────────────────
  function filteredSchedules() {
    const query = state.search.trim().toLowerCase();
    return state.schedules.filter((schedule) => {
      if (state.filterKind !== "all" && schedule.schedule_kind !== state.filterKind) return false;
      if (state.filterState === "on" && (!schedule.enabled || schedule.paused)) return false;
      if (state.filterState === "off" && schedule.enabled) return false;
      if (state.filterState === "paused" && !schedule.paused) return false;
      if (state.filterState === "attention" && !(schedule.issues || []).length) return false;
      if (query) {
        const haystack = `${schedule.name} ${schedule.system_name} ${schedule.system_code}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
  }

  function stateBadge(schedule) {
    if (schedule.paused) {
      return `<span class="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-700" title="${esc(absTime(schedule.paused_until))} 까지 일시 중지">일시 중지</span>`;
    }
    if (!schedule.enabled) {
      return '<span class="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-bold text-gray-500">꺼짐</span>';
    }
    return "";
  }

  function targetLabel(schedule) {
    if (schedule.schedule_kind === "suite") {
      const count = schedule.selected_system_count ?? schedule.step_total;
      return count != null ? `시스템 ${count}개` : "전체 시스템";
    }
    return schedule.module_count != null ? `모듈 ${schedule.module_count}개` : "전체 모듈";
  }

  function renderTable() {
    const body = $("#schedc-table-body");
    const items = filteredSchedules();
    // 다음 실행이 임박한 순(꺼짐/중지는 뒤로).
    items.sort((a, b) => {
      const aKey = a.enabled && !a.paused && a.next_run_at ? new Date(a.next_run_at).getTime() : Infinity;
      const bKey = b.enabled && !b.paused && b.next_run_at ? new Date(b.next_run_at).getTime() : Infinity;
      return aKey - bKey || new Date(b.created_at) - new Date(a.created_at);
    });
    $("#schedc-visible-count").textContent =
      state.view === "list" ? `${items.length}개 예약 표시 중` : "";
    body.innerHTML = "";
    $("#schedc-list-empty").classList.toggle("hidden", items.length > 0);

    for (const schedule of items) {
      const isSuite = schedule.schedule_kind === "suite";
      const status = lastStatus(schedule);
      const issues = schedule.issues || [];
      const row = document.createElement("tr");
      row.className = "cursor-pointer transition hover:bg-indigo-50/40";
      row.dataset.scheduleId = schedule.schedule_id;

      const issueDots = issues
        .map((issue) => `<span title="${esc(ISSUE_META[issue.type]?.label || issue.type)}">${ISSUE_META[issue.type]?.icon || ""}</span>`)
        .join("");
      const link = scheduleLink(schedule);
      const badge = status
        ? `<span class="rounded-full px-2 py-0.5 text-[11px] font-bold ${BADGE_CLASS[status] || "bg-gray-100 text-gray-500"}">${STATUS_LABELS[status] || status}</span>`
        : '<span class="text-[11px] text-gray-300">실행 전</span>';

      row.innerHTML = `
        <td class="px-4 py-3">
          <div class="flex items-center gap-2">
            <span class="rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${isSuite ? "bg-violet-100 text-violet-700" : "bg-indigo-50 text-indigo-600"}">${isSuite ? "SUITE" : esc(schedule.system_code.toUpperCase())}</span>
            <span class="truncate text-sm font-bold text-gray-900">${esc(schedule.name || schedule.system_name)}</span>
            ${issueDots ? `<span class="text-xs">${issueDots}</span>` : ""}
            ${stateBadge(schedule)}
          </div>
          <p class="mt-0.5 text-[11px] text-gray-400">${esc(schedule.system_name)} · ${esc(targetLabel(schedule))}${schedule.auth_method ? ` · ${esc(schedule.auth_method)}` : ""}</p>
        </td>
        <td class="px-4 py-3">
          <p class="text-sm font-semibold text-gray-700">${esc(schedule.cron_label || schedule.cron)}</p>
          <code class="text-[10px] text-gray-400">${esc(schedule.cron)}</code>
        </td>
        <td class="px-4 py-3" data-cell="next">
          ${nextRunCell(schedule)}
        </td>
        <td class="px-4 py-3">
          ${link ? `<a href="${esc(link)}" class="inline-flex items-center gap-1 hover:underline" data-stop>${badge}</a>` : badge}
          ${schedule.last_run_at ? `<p class="mt-0.5 text-[11px] text-gray-400">${relTime(schedule.last_run_at)}</p>` : ""}
        </td>
        <td class="px-4 py-3">
          <div class="flex items-center justify-end gap-1.5" data-stop>
            <button type="button" class="schedc-switch" role="switch" aria-checked="${schedule.enabled}" data-action="toggle" title="켜기/끄기"></button>
            <button type="button" data-action="run-now" title="지금 실행" class="rounded-lg p-1.5 text-gray-400 transition hover:bg-indigo-50 hover:text-indigo-600">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z"/></svg>
            </button>
            <button type="button" data-action="edit" title="상세/수정" class="rounded-lg p-1.5 text-gray-400 transition hover:bg-indigo-50 hover:text-indigo-600">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125"/></svg>
            </button>
            <button type="button" data-action="duplicate" title="복제해서 새 예약" class="rounded-lg p-1.5 text-gray-400 transition hover:bg-indigo-50 hover:text-indigo-600">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5a3.375 3.375 0 00-3.375-3.375H9.75"/></svg>
            </button>
            <button type="button" data-action="delete" title="삭제" class="rounded-lg p-1.5 text-gray-400 transition hover:bg-red-50 hover:text-red-600">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
            </button>
          </div>
        </td>`;

      row.addEventListener("click", (event) => {
        if (event.target.closest("[data-stop]")) return;
        openDrawer(schedule.schedule_id);
      });
      $('[data-action="toggle"]', row).addEventListener("click", (event) => {
        toggleSchedule(schedule.schedule_id, event.currentTarget);
      });
      $('[data-action="run-now"]', row).addEventListener("click", () => runNow(schedule));
      $('[data-action="edit"]', row).addEventListener("click", () => openDrawer(schedule.schedule_id, { edit: true }));
      $('[data-action="duplicate"]', row).addEventListener("click", () => duplicateSchedule(schedule));
      $('[data-action="delete"]', row).addEventListener("click", () => deleteSchedule(schedule));
      body.appendChild(row);
    }
  }

  function nextRunCell(schedule) {
    if (schedule.paused) {
      return `<p class="text-sm font-semibold text-sky-600">일시 중지</p><p class="text-[11px] text-gray-400">${esc(absTime(schedule.paused_until))} 재개</p>`;
    }
    if (!schedule.enabled || !schedule.next_run_at) {
      return '<p class="text-sm text-gray-300">–</p>';
    }
    return `<p class="font-mono text-sm font-bold text-gray-900" data-countdown="${esc(schedule.next_run_at)}">${countdown(schedule.next_run_at)}</p><p class="text-[11px] text-gray-400">${esc(absTime(schedule.next_run_at))}</p>`;
  }

  // 카운트다운 30초 주기 갱신(재렌더 없이 텍스트만).
  setInterval(() => {
    for (const node of $$("[data-countdown]", root)) {
      node.textContent = countdown(node.dataset.countdown) ?? "–";
    }
  }, 30000);

  // ── 행/드로어 공용 동작 ────────────────────────────────────────────────
  async function toggleSchedule(scheduleId, switchNode = null) {
    if (switchNode) switchNode.dataset.busy = "1";
    try {
      await api(`/api/schedules/${scheduleId}/toggle`, { method: "POST" });
      await loadBoard({ silent: true });
      if (state.drawerId === scheduleId) await openDrawer(scheduleId, { keepScroll: true });
    } catch (error) {
      toast(error.message);
    } finally {
      if (switchNode) delete switchNode.dataset.busy;
    }
  }

  async function runNow(schedule) {
    try {
      const result = await api(`/api/schedules/${schedule.schedule_id}/run-now`, { method: "POST" });
      toast("점검을 시작했습니다.", "success");
      if (result.schedule_kind === "suite" && result.suite_id) {
        window.location.href = `/suites/${result.suite_id}`;
      } else if (result.run_id) {
        window.location.href = `/runs/${result.run_id}`;
      }
    } catch (error) {
      toast(error.message);
    }
  }

  async function duplicateSchedule(schedule) {
    try {
      await api(`/api/schedules/${schedule.schedule_id}/duplicate`, { method: "POST" });
      toast("복사본을 만들었습니다. 검토 후 켜 주세요.", "success");
      await loadBoard({ silent: true });
    } catch (error) {
      toast(error.message);
    }
  }

  async function deleteSchedule(schedule) {
    const label = schedule.name || schedule.system_name;
    if (!window.confirm(`'${label}' 예약을 삭제할까요?\n모바일 즉시 점검 URL도 함께 폐기됩니다.`)) return;
    try {
      await api(`/api/schedules/${schedule.schedule_id}`, { method: "DELETE" });
      toast("예약을 삭제했습니다.", "success");
      if (state.drawerId === schedule.schedule_id) closeDrawer();
      await loadBoard({ silent: true });
    } catch (error) {
      toast(error.message);
    }
  }

  // ── 캘린더 뷰 (계획 vs 실적) ───────────────────────────────────────────
  function weekRange(offset) {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const dow = (start.getDay() + 6) % 7; // 월요일 시작
    start.setDate(start.getDate() - dow + offset * 7);
    const end = new Date(start);
    end.setDate(end.getDate() + 7);
    return { start, end };
  }

  async function loadCalendar() {
    const { start, end } = weekRange(state.weekOffset);
    $("#schedc-week-label").textContent =
      `${start.toLocaleDateString("ko-KR", { month: "long", day: "numeric" })} – ${new Date(end.getTime() - 1).toLocaleDateString("ko-KR", { month: "long", day: "numeric" })}`;
    try {
      state.calendar = await api(
        `/api/schedules/calendar?from=${encodeURIComponent(start.toISOString())}&to=${encodeURIComponent(end.toISOString())}`
      );
      renderCalendar();
    } catch (error) {
      toast(error.message);
    }
  }

  function renderCalendar() {
    const data = state.calendar;
    if (!data) return;
    renderCoverage(data);

    const { start } = weekRange(state.weekOffset);
    const days = Array.from({ length: 7 }, (_, i) => {
      const date = new Date(start);
      date.setDate(date.getDate() + i);
      return date;
    });
    const todayKey = new Date().toDateString();

    // 블록을 (일자 index, 시) 로 버킷팅
    const buckets = new Map();
    const hoursWithContent = new Set();
    for (const block of data.blocks || []) {
      const at = new Date(block.at);
      const dayIndex = Math.floor((at - start) / 86400000);
      if (dayIndex < 0 || dayIndex > 6) continue;
      const key = `${dayIndex}:${at.getHours()}`;
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(block);
      hoursWithContent.add(at.getHours());
    }

    const grid = $("#schedc-calendar-grid");
    const empty = $("#schedc-calendar-empty");
    grid.innerHTML = "";
    if (!hoursWithContent.size) {
      grid.classList.add("hidden");
      empty.classList.remove("hidden");
      return;
    }
    grid.classList.remove("hidden");
    empty.classList.add("hidden");

    const hours = Array.from(hoursWithContent).sort((a, b) => a - b);
    const table = document.createElement("div");
    table.className = "schedc-cal-grid min-w-[720px] gap-px overflow-hidden rounded-xl bg-gray-100 ring-1 ring-gray-100";

    // 헤더 행
    table.appendChild(Object.assign(document.createElement("div"), { className: "bg-white" }));
    for (const [index, date] of days.entries()) {
      const isToday = date.toDateString() === todayKey;
      const head = document.createElement("div");
      head.className = `bg-white px-2 py-2 text-center ${isToday ? "bg-indigo-50/70" : ""}`;
      head.innerHTML = `<p class="text-[10px] font-bold ${isToday ? "text-indigo-600" : "text-gray-400"}">${DOW_LABELS[date.getDay()]}</p><p class="text-xs font-bold ${isToday ? "text-indigo-700" : "text-gray-700"}">${date.getDate()}</p>`;
      table.appendChild(head);
    }

    for (const hour of hours) {
      const label = document.createElement("div");
      label.className = "flex items-start justify-end bg-white px-1.5 py-1.5";
      label.innerHTML = `<span class="text-[10px] font-semibold text-gray-400">${String(hour).padStart(2, "0")}시</span>`;
      table.appendChild(label);
      for (let dayIndex = 0; dayIndex < 7; dayIndex += 1) {
        const cell = document.createElement("div");
        const isToday = days[dayIndex].toDateString() === todayKey;
        cell.className = `min-h-[2.25rem] space-y-0.5 bg-white p-1 ${isToday ? "bg-indigo-50/40" : ""}`;
        for (const block of buckets.get(`${dayIndex}:${hour}`) || []) {
          cell.appendChild(calendarBlock(block));
        }
        table.appendChild(cell);
      }
    }
    grid.appendChild(table);
  }

  function calendarBlock(block) {
    const at = new Date(block.at);
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "schedc-block w-full";
    chip.dataset.state = block.state;
    if (block.schedule_kind === "suite") chip.dataset.suite = "1";
    if (block.unplanned) chip.dataset.unplanned = "1";
    const stateLabel =
      block.state === "planned" ? "예정" :
      block.state === "missed" ? "누락" :
      block.state === "active" ? "진행 중" :
      STATUS_LABELS[block.state] || block.state;
    chip.title = `${block.name} · ${at.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false })} · ${stateLabel}${block.unplanned ? " (수동 실행)" : ""}`;
    chip.innerHTML = `<span class="truncate">${esc(block.name)}</span><span class="ml-auto shrink-0 font-mono font-normal opacity-70">${String(at.getMinutes()).padStart(2, "0") === "00" ? `${String(at.getHours()).padStart(2, "0")}시` : `:${String(at.getMinutes()).padStart(2, "0")}`}</span>`;
    chip.addEventListener("click", () => {
      if (block.link && block.state !== "planned" && block.state !== "missed") {
        window.location.href = block.link;
        return;
      }
      openDrawer(block.schedule_id);
    });
    return chip;
  }

  function renderCoverage(data) {
    const wrap = $("#schedc-coverage");
    wrap.innerHTML = "";
    for (const entry of data.coverage || []) {
      const chip = document.createElement("span");
      chip.className = `inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold ${entry.covered ? "bg-green-50 text-green-700 ring-1 ring-green-100" : "bg-red-50 text-red-700 ring-1 ring-red-100"}`;
      chip.title = entry.last_checked_at
        ? `마지막 점검 ${relTime(entry.last_checked_at)}`
        : "점검 이력이 없습니다";
      chip.innerHTML = `${entry.covered ? "✓" : "✕"} ${esc(entry.system_name)}`;
      wrap.appendChild(chip);
    }
    const warnings = data.cluster_warnings || [];
    const warningNode = $("#schedc-cluster-warnings");
    if (warnings.length) {
      warningNode.classList.remove("hidden");
      warningNode.textContent =
        "⚠ 몰림 주의: " +
        warnings.map((w) => `${w.label} (예약 ${w.schedule_count}개)`).join(" · ") +
        " — 같은 시각에 점검이 몰리면 순차 실행 대기로 누락이 생길 수 있습니다.";
    } else {
      warningNode.classList.add("hidden");
    }
  }

  // ── 상세 드로어 (라이프사이클 매니저) ──────────────────────────────────
  async function openDrawer(scheduleId, { edit = false, keepScroll = false } = {}) {
    state.drawerId = scheduleId;
    root.classList.add("is-drawer-open");
    const body = $("#schedc-drawer-body");
    const previousScroll = keepScroll ? body.scrollTop : 0;
    body.innerHTML = '<p class="py-10 text-center text-sm text-gray-400">불러오는 중…</p>';
    try {
      const [detail, history] = await Promise.all([
        api(`/api/schedules/${scheduleId}`),
        api(`/api/schedules/${scheduleId}/history`),
      ]);
      if (state.drawerId !== scheduleId) return;
      state.drawerDetail = detail;
      renderDrawer(detail, history, { edit });
      body.scrollTop = previousScroll;
    } catch (error) {
      body.innerHTML = `<p class="py-10 text-center text-sm text-red-500">${esc(error.message)}</p>`;
    }
  }

  function closeDrawer() {
    state.drawerId = null;
    state.editState = null;
    root.classList.remove("is-drawer-open");
  }

  function renderDrawer(detail, history, { edit = false } = {}) {
    const isSuite = detail.schedule_kind === "suite";
    $("#schedc-drawer-kind").textContent = isSuite ? "SUITE" : detail.system_code.toUpperCase();
    $("#schedc-drawer-kind").className = `rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white ${isSuite ? "bg-violet-600" : "bg-indigo-600"}`;
    $("#schedc-drawer-system").textContent = detail.system_name;
    $("#schedc-drawer-title").textContent = detail.name || detail.system_name;
    $("#schedc-drawer-sub").textContent =
      `${detail.cron_label || detail.cron} · ${detail.timezone}` +
      (detail.created_by_user_name ? ` · ${detail.created_by_user_name} 등록` : "");
    const toggle = $("#schedc-drawer-toggle");
    toggle.setAttribute("aria-checked", String(detail.enabled));
    toggle.onclick = () => toggleSchedule(detail.schedule_id, toggle);

    const stats = history?.stats || {};
    const body = $("#schedc-drawer-body");
    body.innerHTML = "";

    // 일시 중지 배너
    if (detail.paused) {
      const banner = document.createElement("div");
      banner.className = "rounded-xl border border-sky-200 bg-sky-50 px-3 py-2.5 text-xs font-semibold text-sky-700";
      banner.innerHTML = `⏸ ${esc(absTime(detail.paused_until))} 까지 일시 중지 중 — 기한이 지나면 자동 재개됩니다.`;
      body.appendChild(banner);
    }

    body.appendChild(drawerSummarySection(detail));
    body.appendChild(drawerHistorySection(stats));
    body.appendChild(drawerActionsSection(detail));
    body.appendChild(drawerPauseSection(detail));
    body.appendChild(drawerEditSection(detail, { open: edit }));
    body.appendChild(drawerChangeLogSection(detail));
  }

  function sectionShell(title, subtitle = "") {
    const section = document.createElement("section");
    section.className = "rounded-2xl border border-gray-100 bg-white p-4 shadow-sm";
    section.innerHTML = `
      <div class="flex items-baseline justify-between gap-2">
        <h3 class="text-sm font-bold text-gray-800">${title}</h3>
        ${subtitle ? `<span class="text-[11px] text-gray-400">${subtitle}</span>` : ""}
      </div>
      <div class="mt-3" data-role="section-body"></div>`;
    return section;
  }

  function drawerSummarySection(detail) {
    const section = sectionShell("다음 실행");
    const body = $('[data-role="section-body"]', section);
    const link = scheduleLink(detail);
    const status = lastStatus(detail);
    body.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <div>
          ${detail.paused
            ? '<p class="text-lg font-bold text-sky-600">일시 중지</p>'
            : detail.enabled && detail.next_run_at
              ? `<p class="font-mono text-lg font-bold text-gray-900" data-countdown="${esc(detail.next_run_at)}">${countdown(detail.next_run_at)}</p>`
              : '<p class="text-lg font-bold text-gray-300">꺼짐</p>'}
          <p class="text-[11px] text-gray-400">${detail.enabled && detail.next_run_at && !detail.paused ? esc(absTime(detail.next_run_at)) : "예약이 켜지면 다음 실행 시각이 계산됩니다"}</p>
        </div>
        <div class="text-right">
          <p class="text-[11px] font-semibold text-gray-400">마지막 결과</p>
          ${status
            ? `${link ? `<a href="${esc(link)}" class="hover:underline">` : ""}<span class="rounded-full px-2 py-0.5 text-[11px] font-bold ${BADGE_CLASS[status] || "bg-gray-100 text-gray-500"}">${STATUS_LABELS[status] || status}</span>${link ? "</a>" : ""}<p class="mt-0.5 text-[11px] text-gray-400">${relTime(detail.last_run_at)}</p>`
            : '<p class="text-xs text-gray-300">실행 전</p>'}
        </div>
      </div>
      ${detail.last_skipped_at ? `<p class="mt-2 rounded-lg bg-amber-50 px-2.5 py-1.5 text-[11px] font-medium text-amber-700">🟡 ${relTime(detail.last_skipped_at)} 직전 실행이 끝나지 않아 주기를 건너뛰었습니다.</p>` : ""}`;
    return section;
  }

  function drawerHistorySection(stats) {
    const section = sectionShell("실행 이력", `최근 ${stats.total || 0}회 — 이 예약은 신뢰할 수 있는가`);
    const body = $('[data-role="section-body"]', section);
    if (!stats.total) {
      body.innerHTML = '<p class="text-xs text-gray-400">아직 이 예약으로 실행된 점검이 없습니다.</p>';
      return section;
    }
    const strip = document.createElement("div");
    strip.className = "flex items-end gap-[3px]";
    for (const dot of stats.dots || []) {
      const stateLabel = dot.state === "active" ? "진행 중" : (STATUS_LABELS[dot.state] || dot.state);
      const node = document.createElement(dot.link ? "a" : "span");
      node.className = "schedc-dot";
      node.dataset.state = dot.state;
      node.title = `${stateLabel} · ${absTime(dot.at)}${dot.duration_ms != null ? ` · ${formatDuration(dot.duration_ms)}` : ""}`;
      if (dot.link) node.href = dot.link;
      strip.appendChild(node);
    }
    body.appendChild(strip);
    const tiles = document.createElement("div");
    tiles.className = "mt-3 grid grid-cols-3 gap-2";
    tiles.innerHTML = `
      <div class="rounded-xl bg-gray-50 p-2.5 text-center">
        <p class="text-[10px] font-semibold text-gray-400">성공률</p>
        <p class="text-base font-bold ${stats.success_rate == null ? "text-gray-300" : stats.success_rate >= 90 ? "text-green-600" : stats.success_rate >= 60 ? "text-amber-600" : "text-red-600"}">${stats.success_rate == null ? "–" : `${stats.success_rate}%`}</p>
      </div>
      <div class="rounded-xl bg-gray-50 p-2.5 text-center">
        <p class="text-[10px] font-semibold text-gray-400">평균 소요</p>
        <p class="text-base font-bold text-gray-800">${formatDuration(stats.avg_duration_ms)}</p>
      </div>
      <div class="rounded-xl bg-gray-50 p-2.5 text-center">
        <p class="text-[10px] font-semibold text-gray-400">연속 성공</p>
        <p class="text-base font-bold text-gray-800">${stats.current_streak}회</p>
      </div>`;
    body.appendChild(tiles);
    return section;
  }

  function drawerActionsSection(detail) {
    const section = sectionShell("동작");
    const body = $('[data-role="section-body"]', section);
    body.className += " flex flex-wrap gap-2";
    const mkButton = (label, classes) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold shadow-sm transition ${classes}`;
      button.textContent = label;
      return button;
    };
    const runButton = mkButton("▶ 지금 실행", "bg-indigo-600 text-white hover:bg-indigo-700");
    runButton.addEventListener("click", () => runNow(detail));
    const duplicateButton = mkButton("⧉ 복제해서 새 예약", "bg-white text-gray-700 ring-1 ring-gray-200 hover:bg-gray-50");
    duplicateButton.addEventListener("click", () => duplicateSchedule(detail));
    const deleteButton = mkButton("삭제", "bg-white text-red-600 ring-1 ring-red-100 hover:bg-red-50");
    deleteButton.addEventListener("click", () => deleteSchedule(detail));
    body.append(runButton, duplicateButton, deleteButton);
    if (detail.trigger_token) {
      const copyButton = mkButton("📱 즉시 점검 URL 복사", "bg-white text-gray-700 ring-1 ring-gray-200 hover:bg-gray-50");
      copyButton.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(`${window.location.origin}/m/${detail.trigger_token}`);
          toast("모바일 즉시 점검 URL을 복사했습니다.", "success");
        } catch (_) {
          toast("클립보드 복사에 실패했습니다.");
        }
      });
      body.appendChild(copyButton);
    }
    return section;
  }

  function drawerPauseSection(detail) {
    const section = sectionShell("일시 중지", "사이트 정기점검 기간 등에 임시로 끄고, 기한이 지나면 자동 재개");
    const body = $('[data-role="section-body"]', section);
    const quick = [["내일까지", 1], ["3일", 3], ["1주일", 7]];
    body.innerHTML = `
      <div class="flex flex-wrap items-center gap-2">
        ${quick.map(([label, days]) => `<button type="button" data-pause-days="${days}" class="rounded-lg bg-gray-100 px-2.5 py-1.5 text-[11px] font-bold text-gray-600 transition hover:bg-gray-200">${label}</button>`).join("")}
        <input type="datetime-local" data-role="pause-until" class="schedc-field !w-auto !py-1.5 !text-xs">
        <button type="button" data-role="pause-apply" class="rounded-lg bg-sky-600 px-3 py-1.5 text-[11px] font-bold text-white transition hover:bg-sky-700">적용</button>
        ${detail.paused ? '<button type="button" data-role="pause-clear" class="rounded-lg bg-white px-3 py-1.5 text-[11px] font-bold text-sky-700 ring-1 ring-sky-200 transition hover:bg-sky-50">지금 재개</button>' : ""}
      </div>`;
    const input = $('[data-role="pause-until"]', body);
    for (const chip of $$("[data-pause-days]", body)) {
      chip.addEventListener("click", () => {
        const until = new Date();
        until.setDate(until.getDate() + Number(chip.dataset.pauseDays));
        until.setSeconds(0, 0);
        const pad = (n) => String(n).padStart(2, "0");
        input.value = `${until.getFullYear()}-${pad(until.getMonth() + 1)}-${pad(until.getDate())}T${pad(until.getHours())}:${pad(until.getMinutes())}`;
      });
    }
    $('[data-role="pause-apply"]', body).addEventListener("click", async () => {
      if (!input.value) { toast("일시 중지 종료 시각을 선택해 주세요."); return; }
      await applyPause(detail.schedule_id, new Date(input.value).toISOString());
    });
    $('[data-role="pause-clear"]', body)?.addEventListener("click", () => applyPause(detail.schedule_id, null));
    return section;
  }

  async function applyPause(scheduleId, pausedUntilIso) {
    try {
      await api(`/api/schedules/${scheduleId}/pause-until`, {
        method: "POST",
        body: JSON.stringify({ paused_until: pausedUntilIso }),
      });
      toast(pausedUntilIso ? "일시 중지를 설정했습니다." : "예약을 재개했습니다.", "success");
      await loadBoard({ silent: true });
      await openDrawer(scheduleId, { keepScroll: true });
    } catch (error) {
      toast(error.message);
    }
  }

  // ── 수정 폼 (이 시스템 최초의 edit — 삭제 후 재생성 없이 제자리 수정) ──
  function parseCronToBuilder(cron) {
    const fields = (cron || "").trim().split(/\s+/);
    const base = { mode: "custom", time: "09:00", dows: [1], dom: 1, every: 1, unit: "hour", raw: cron };
    if (fields.length !== 5) return base;
    const [minute, hour, dom, month, dow] = fields;
    if (month !== "*") return base;
    if (minute.startsWith("*/") && hour === "*" && dom === "*" && dow === "*") {
      return { ...base, mode: "interval", every: Number(minute.slice(2)) || 1, unit: "minute" };
    }
    if (/^\d+$/.test(minute) && hour.startsWith("*/") && dom === "*" && dow === "*") {
      return { ...base, mode: "interval", every: Number(hour.slice(2)) || 1, unit: "hour" };
    }
    if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) return base;
    const time = `${String(Number(hour)).padStart(2, "0")}:${String(Number(minute)).padStart(2, "0")}`;
    if (dom === "*" && dow === "*") return { ...base, mode: "daily", time };
    if (dom === "*" && dow === "1-5") return { ...base, mode: "weekdays", time };
    if (dom === "*" && /^\d+(,\d+)*$/.test(dow)) {
      return { ...base, mode: "weekly", time, dows: dow.split(",").map((d) => Number(d) % 7) };
    }
    if (dow === "*" && /^\d+$/.test(dom)) return { ...base, mode: "monthly", time, dom: Number(dom) };
    return base;
  }

  function builderToCron(builder) {
    if (builder.mode === "custom") {
      return { cron: builder.raw.trim(), label: builder.raw.trim() };
    }
    if (builder.mode === "interval") {
      const every = Math.max(1, Math.min(builder.unit === "minute" ? 59 : 23, builder.every || 1));
      return builder.unit === "minute"
        ? { cron: `*/${every} * * * *`, label: `${every}분마다` }
        : { cron: `0 */${every} * * *`, label: `${every}시간마다` };
    }
    const [hour, minute] = (builder.time || "09:00").split(":").map(Number);
    const timeLabel = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
    switch (builder.mode) {
      case "daily": return { cron: `${minute} ${hour} * * *`, label: `매일 ${timeLabel}` };
      case "weekdays": return { cron: `${minute} ${hour} * * 1-5`, label: `평일 ${timeLabel}` };
      case "weekly": {
        const dows = [...new Set(builder.dows)].sort();
        if (!dows.length) return { cron: null, label: "요일을 선택해 주세요" };
        return {
          cron: `${minute} ${hour} * * ${dows.join(",")}`,
          label: `매주 ${dows.map((d) => DOW_LABELS[d]).join("·")} ${timeLabel}`,
        };
      }
      case "monthly": return { cron: `${minute} ${hour} ${builder.dom} * *`, label: `매월 ${builder.dom}일 ${timeLabel}` };
      default: return { cron: null, label: "" };
    }
  }

  function drawerEditSection(detail, { open = false } = {}) {
    const isSuite = detail.schedule_kind === "suite";
    const section = document.createElement("details");
    section.className = "group rounded-2xl border border-gray-100 bg-white shadow-sm";
    if (open) section.open = true;
    section.innerHTML = `
      <summary class="flex cursor-pointer items-center justify-between px-4 py-3.5 text-sm font-bold text-gray-800">
        <span>✏️ 예약 수정</span>
        <svg class="h-4 w-4 text-gray-400 transition group-open:rotate-180" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5"/></svg>
      </summary>
      <div class="space-y-4 border-t border-gray-100 px-4 py-4" data-role="edit-body"></div>`;
    const body = $('[data-role="edit-body"]', section);

    const builder = parseCronToBuilder(detail.cron);
    state.editState = { builder };

    // 이름
    const nameField = document.createElement("label");
    nameField.className = "block";
    nameField.innerHTML = `<span class="text-[11px] font-semibold text-gray-500">예약 이름</span>
      <input type="text" data-edit="name" value="${esc(detail.name)}" placeholder="${esc(detail.system_name)}" class="schedc-field mt-1">`;
    body.appendChild(nameField);

    // cron 빌더
    const cronWrap = document.createElement("div");
    cronWrap.innerHTML = `
      <span class="text-[11px] font-semibold text-gray-500">반복 주기</span>
      <div class="schedc-seg schedc-seg--sm mt-1 flex-wrap" data-role="cron-modes">
        ${[["daily", "매일"], ["weekdays", "평일"], ["weekly", "매주"], ["monthly", "매월"], ["interval", "주기 반복"], ["custom", "직접 입력"]]
          .map(([mode, label]) => `<button type="button" data-cron-mode="${mode}" aria-pressed="${builder.mode === mode}" class="schedc-seg__btn">${label}</button>`).join("")}
      </div>
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <input type="time" data-cron="time" value="${esc(builder.time)}" class="schedc-field !w-auto !py-1.5 !text-xs">
        <div class="flex gap-1" data-cron="dows">
          ${[1, 2, 3, 4, 5, 6, 0].map((d) => `<button type="button" data-dow="${d}" aria-pressed="${builder.dows.includes(d)}" class="schedc-dow-chip">${DOW_LABELS[d]}</button>`).join("")}
        </div>
        <select data-cron="dom" class="schedc-field !w-auto !py-1.5 !text-xs">
          ${Array.from({ length: 28 }, (_, i) => `<option value="${i + 1}" ${builder.dom === i + 1 ? "selected" : ""}>${i + 1}일</option>`).join("")}
        </select>
        <span class="flex items-center gap-1.5" data-cron="interval">
          <input type="number" min="1" max="59" data-cron="every" value="${builder.every}" class="schedc-field !w-16 !py-1.5 !text-xs">
          <span class="schedc-seg schedc-seg--sm">
            <button type="button" data-unit="minute" aria-pressed="${builder.unit === "minute"}" class="schedc-seg__btn">분</button>
            <button type="button" data-unit="hour" aria-pressed="${builder.unit === "hour"}" class="schedc-seg__btn">시간</button>
          </span>
        </span>
        <input type="text" data-cron="raw" value="${esc(builder.raw)}" placeholder="분 시 일 월 요일" class="schedc-field !w-40 !py-1.5 font-mono !text-xs">
      </div>
      <p class="mt-2 flex items-center gap-2 text-xs">
        <span class="font-semibold text-gray-700" data-cron="label"></span>
        <code class="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-500" data-cron="preview"></code>
      </p>`;
    body.appendChild(cronWrap);
    bindCronBuilder(cronWrap, builder);

    if (!isSuite) {
      body.appendChild(editModulesBlock(detail));
      body.appendChild(editAuthBlock(detail));
    } else {
      body.appendChild(editSuiteBlock(detail));
    }

    const footer = document.createElement("div");
    footer.className = "flex items-center justify-end gap-2 border-t border-gray-100 pt-3";
    footer.innerHTML = `
      <p class="mr-auto text-[11px] text-gray-400">저장하면 다음 실행 시각이 새 주기로 다시 계산됩니다.</p>
      <button type="button" data-role="edit-save" class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-bold text-white shadow-sm transition hover:bg-indigo-700 disabled:opacity-50">저장</button>`;
    $('[data-role="edit-save"]', footer).addEventListener("click", () => saveEdit(detail, section));
    body.appendChild(footer);
    return section;
  }

  function bindCronBuilder(wrap, builder) {
    const refresh = () => {
      for (const button of $$("[data-cron-mode]", wrap)) {
        button.setAttribute("aria-pressed", String(button.dataset.cronMode === builder.mode));
      }
      const usesTime = ["daily", "weekdays", "weekly", "monthly"].includes(builder.mode);
      $('[data-cron="time"]', wrap).classList.toggle("hidden", !usesTime);
      $('[data-cron="dows"]', wrap).classList.toggle("hidden", builder.mode !== "weekly");
      $('[data-cron="dom"]', wrap).classList.toggle("hidden", builder.mode !== "monthly");
      $('[data-cron="interval"]', wrap).classList.toggle("hidden", builder.mode !== "interval");
      $('[data-cron="raw"]', wrap).classList.toggle("hidden", builder.mode !== "custom");
      const built = builderToCron(builder);
      $('[data-cron="label"]', wrap).textContent = built.cron ? built.label : built.label || "—";
      $('[data-cron="preview"]', wrap).textContent = built.cron || "—";
    };
    for (const button of $$("[data-cron-mode]", wrap)) {
      button.addEventListener("click", () => { builder.mode = button.dataset.cronMode; refresh(); });
    }
    $('[data-cron="time"]', wrap).addEventListener("input", (event) => { builder.time = event.target.value || "09:00"; refresh(); });
    for (const chip of $$("[data-dow]", wrap)) {
      chip.addEventListener("click", () => {
        const dow = Number(chip.dataset.dow);
        builder.dows = builder.dows.includes(dow)
          ? builder.dows.filter((d) => d !== dow)
          : [...builder.dows, dow];
        chip.setAttribute("aria-pressed", String(builder.dows.includes(dow)));
        refresh();
      });
    }
    $('[data-cron="dom"]', wrap).addEventListener("change", (event) => { builder.dom = Number(event.target.value); refresh(); });
    $('[data-cron="every"]', wrap).addEventListener("input", (event) => { builder.every = Number(event.target.value) || 1; refresh(); });
    for (const button of $$("[data-unit]", wrap)) {
      button.addEventListener("click", () => {
        builder.unit = button.dataset.unit;
        for (const sibling of $$("[data-unit]", wrap)) {
          sibling.setAttribute("aria-pressed", String(sibling === button));
        }
        refresh();
      });
    }
    $('[data-cron="raw"]', wrap).addEventListener("input", (event) => { builder.raw = event.target.value; refresh(); });
    refresh();
  }

  function editModulesBlock(detail) {
    const wrap = document.createElement("div");
    const system = SYSTEMS[detail.system_code];
    const modules = system?.modules || [];
    const selected = new Set(
      (detail.selected_module_ids?.length ? detail.selected_module_ids : modules.map((m) => m.module_id)),
    );
    wrap.innerHTML = `<span class="text-[11px] font-semibold text-gray-500">모듈 선택</span>
      <div class="mt-1.5 grid grid-cols-2 gap-1.5" data-role="module-list"></div>`;
    const list = $('[data-role="module-list"]', wrap);
    if (!modules.length) {
      list.innerHTML = '<p class="col-span-2 text-[11px] text-gray-400">모듈 정보를 불러올 수 없어 기존 선택이 유지됩니다.</p>';
      return wrap;
    }
    for (const module of modules) {
      const label = document.createElement("label");
      label.className = "flex items-center gap-2 rounded-lg border border-gray-100 bg-gray-50/60 px-2.5 py-1.5 text-xs font-medium text-gray-700";
      label.innerHTML = `<input type="checkbox" data-module-id="${esc(module.module_id)}" ${selected.has(module.module_id) ? "checked" : ""} class="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600">
        <span class="truncate" title="${esc(module.name)}">${esc(module.name)}</span>`;
      list.appendChild(label);
    }
    return wrap;
  }

  function editAuthBlock(detail) {
    const wrap = document.createElement("div");
    const system = SYSTEMS[detail.system_code];
    const form = (system?.run_form || []).filter((field) => field.key !== "browser_mode");
    wrap.innerHTML = `<span class="text-[11px] font-semibold text-gray-500">인증값 교체</span>
      <p class="mt-0.5 text-[11px] text-gray-400">저장된 값은 보안상 표시하지 않습니다. 바꿀 값만 입력하면 그 값만 교체됩니다.</p>
      <div class="mt-1.5 grid grid-cols-2 gap-2" data-role="auth-fields"></div>`;
    const list = $('[data-role="auth-fields"]', wrap);
    if (!form.length) {
      list.innerHTML = '<p class="col-span-2 text-[11px] text-gray-400">이 시스템은 수정 가능한 입력값이 없습니다.</p>';
      return wrap;
    }
    const currentAuth = detail.auth_method || "";
    const effectiveAuth = () => $('select[data-auth-key="auth_method"]', list)?.value || currentAuth;
    const applyVisibility = () => {
      const auth = effectiveAuth();
      for (const node of $$("[data-show-when]", list)) {
        const allowed = JSON.parse(node.dataset.showWhen);
        node.classList.toggle("hidden", allowed.length > 0 && !allowed.includes(auth));
      }
    };
    for (const field of form) {
      const holder = document.createElement("label");
      holder.className = "block";
      const showWhen = field.show_when?.auth_method;
      if (showWhen) {
        holder.dataset.showWhen = JSON.stringify(Array.isArray(showWhen) ? showWhen : [showWhen]);
      } else {
        holder.dataset.showWhen = "[]";
      }
      const stored = (detail.input_data_keys || []).includes(field.key);
      if (field.type === "select") {
        const isAuthMethod = field.key === "auth_method";
        holder.innerHTML = `<span class="text-[11px] font-semibold text-gray-500">${esc(field.label)}</span>
          <select data-auth-key="${esc(field.key)}" class="schedc-field mt-1 !py-1.5 !text-xs">
            ${isAuthMethod ? "" : '<option value="">저장된 값 유지</option>'}
            ${(field.options || []).map((option) => `<option value="${esc(option.value)}" ${isAuthMethod && option.value === currentAuth ? "selected" : ""}>${esc(option.label)}</option>`).join("")}
          </select>`;
      } else {
        holder.innerHTML = `<span class="text-[11px] font-semibold text-gray-500">${esc(field.label)}</span>
          <input type="${field.type === "password" ? "password" : "text"}" data-auth-key="${esc(field.key)}"
                 placeholder="${stored ? "저장된 값 유지" : esc(field.placeholder || "")}" class="schedc-field mt-1 !py-1.5 !text-xs">`;
      }
      list.appendChild(holder);
    }
    $('select[data-auth-key="auth_method"]', list)?.addEventListener("change", applyVisibility);
    applyVisibility();
    return wrap;
  }

  function editSuiteBlock(detail) {
    const wrap = document.createElement("div");
    const selected = new Set(detail.selected_system_codes || []);
    const entries = Object.values(SYSTEMS);
    wrap.innerHTML = `<span class="text-[11px] font-semibold text-gray-500">점검할 시스템</span>
      <div class="mt-1.5 grid grid-cols-2 gap-1.5" data-role="suite-systems"></div>
      <label class="mt-3 block">
        <span class="text-[11px] font-semibold text-gray-500">브라우저 모드</span>
        <select data-role="suite-browser-mode" class="schedc-field mt-1 !w-auto !py-1.5 !text-xs">
          <option value="headed" ${detail.browser_mode === "headed" ? "selected" : ""}>실제 브라우저 창 열기</option>
          <option value="headless" ${detail.browser_mode === "headless" ? "selected" : ""}>백그라운드 실행</option>
        </select>
      </label>
      <p class="mt-1 text-[11px] text-gray-400">시스템별 저장된 인증 프리셋은 그대로 유지됩니다. 시스템을 새로 추가하려면 프리셋이 필요해 실행 화면에서 다시 등록해 주세요.</p>`;
    const list = $('[data-role="suite-systems"]', wrap);
    for (const system of entries) {
      const label = document.createElement("label");
      label.className = "flex items-center gap-2 rounded-lg border border-gray-100 bg-gray-50/60 px-2.5 py-1.5 text-xs font-medium text-gray-700";
      label.innerHTML = `<input type="checkbox" data-system-code="${esc(system.system_code)}" ${selected.has(system.system_code) ? "checked" : ""} class="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600">
        <span class="truncate">${esc(system.name)}</span>`;
      list.appendChild(label);
    }
    return wrap;
  }

  async function saveEdit(detail, section) {
    const isSuite = detail.schedule_kind === "suite";
    const payload = {};

    const name = $('[data-edit="name"]', section)?.value ?? "";
    if (name.trim() !== detail.name) payload.name = name.trim();

    const built = builderToCron(state.editState.builder);
    if (!built.cron) { toast("반복 주기를 완성해 주세요."); return; }
    if (built.cron !== detail.cron) payload.cron = built.cron;

    if (!isSuite) {
      const moduleBoxes = $$("[data-module-id]", section);
      if (moduleBoxes.length) {
        const chosen = moduleBoxes.filter((box) => box.checked).map((box) => box.dataset.moduleId);
        if (!chosen.length) { toast("모듈을 1개 이상 선택해 주세요."); return; }
        const original = detail.selected_module_ids?.length
          ? detail.selected_module_ids
          : moduleBoxes.map((box) => box.dataset.moduleId);
        if (JSON.stringify(chosen) !== JSON.stringify(original)) payload.selected_module_ids = chosen;
      }
      const inputData = {};
      for (const field of $$("[data-auth-key]", section)) {
        if (field.closest(".hidden")) continue;
        const value = (field.value || "").trim();
        if (!value) continue;
        if (field.dataset.authKey === "auth_method" && value === (detail.auth_method || "")) continue;
        inputData[field.dataset.authKey] = value;
      }
      if (Object.keys(inputData).length) payload.input_data = inputData;
    } else {
      const chosen = $$("[data-system-code]", section)
        .filter((box) => box.checked)
        .map((box) => box.dataset.systemCode);
      if (!chosen.length) { toast("시스템을 1개 이상 선택해 주세요."); return; }
      if (JSON.stringify([...chosen].sort()) !== JSON.stringify([...(detail.selected_system_codes || [])].sort())) {
        payload.selected_system_codes = chosen;
      }
      const browserMode = $('[data-role="suite-browser-mode"]', section)?.value;
      if (browserMode && browserMode !== detail.browser_mode) payload.browser_mode = browserMode;
    }

    if (!Object.keys(payload).length) {
      toast("변경된 내용이 없습니다.", "success");
      return;
    }
    const saveButton = $('[data-role="edit-save"]', section);
    saveButton.disabled = true;
    try {
      await api(`/api/schedules/${detail.schedule_id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      toast("예약을 수정했습니다.", "success");
      await loadBoard({ silent: true });
      await openDrawer(detail.schedule_id, { keepScroll: true });
    } catch (error) {
      toast(error.message);
      saveButton.disabled = false;
    }
  }

  function drawerChangeLogSection(detail) {
    const section = sectionShell("변경 이력", "누가 언제 수정했나");
    const body = $('[data-role="section-body"]', section);
    const entries = detail.change_log || [];
    if (!entries.length) {
      body.innerHTML = '<p class="text-xs text-gray-400">기록된 변경 이력이 없습니다.</p>';
      return section;
    }
    const list = document.createElement("ol");
    list.className = "space-y-2";
    for (const entry of entries) {
      const item = document.createElement("li");
      item.className = "flex items-start gap-2 text-xs";
      item.innerHTML = `
        <span class="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-300"></span>
        <div class="min-w-0">
          <p class="font-semibold text-gray-700">${esc(CHANGE_ACTION_LABELS[entry.action] || entry.action)}${entry.detail ? ` — <span class="font-normal text-gray-500">${esc(entry.detail)}</span>` : ""}</p>
          <p class="text-[11px] text-gray-400">${entry.user_name ? `${esc(entry.user_name)} · ` : ""}${absTime(entry.at)}</p>
        </div>`;
      list.appendChild(item);
    }
    body.appendChild(list);
    return section;
  }

  // ── 뷰 전환 / 필터 / 이벤트 바인딩 ─────────────────────────────────────
  function setView(view) {
    state.view = view;
    for (const button of $$("[data-view-btn]", root)) {
      button.setAttribute("aria-pressed", String(button.dataset.viewBtn === view));
    }
    $("#schedc-list-view").classList.toggle("hidden", view !== "list");
    $("#schedc-calendar-view").classList.toggle("hidden", view !== "calendar");
    for (const node of $$("[data-list-only]", root)) {
      node.classList.toggle("hidden", view !== "list");
    }
    if (view === "calendar") loadCalendar();
    else renderTable();
  }

  for (const button of $$("[data-view-btn]", root)) {
    button.addEventListener("click", () => setView(button.dataset.viewBtn));
  }
  $("#schedc-search").addEventListener("input", (event) => { state.search = event.target.value; renderTable(); });
  $("#schedc-filter-kind").addEventListener("change", (event) => { state.filterKind = event.target.value; renderTable(); });
  $("#schedc-filter-state").addEventListener("change", (event) => { state.filterState = event.target.value; renderTable(); });
  $("#schedc-refresh").addEventListener("click", () => {
    loadBoard();
    if (state.view === "calendar") loadCalendar();
  });
  $("#schedc-kpi-attention").addEventListener("click", () => {
    setView("list");
    $("#schedc-filter-state").value = "attention";
    state.filterState = "attention";
    renderTable();
    $("#schedc-attention")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("#schedc-week-prev").addEventListener("click", () => { state.weekOffset -= 1; loadCalendar(); });
  $("#schedc-week-next").addEventListener("click", () => { state.weekOffset += 1; loadCalendar(); });
  $("#schedc-week-today").addEventListener("click", () => { state.weekOffset = 0; loadCalendar(); });
  $("#schedc-drawer-close").addEventListener("click", closeDrawer);
  $("#schedc-drawer-backdrop").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.drawerId) closeDrawer();
  });

  // 60초 주기 자동 갱신(관제실은 방치 화면 — 조용히 최신 상태 유지).
  setInterval(() => {
    loadBoard({ silent: true });
    if (state.view === "calendar") loadCalendar();
  }, 60000);

  loadBoard();
  const openScheduleId = new URLSearchParams(location.search).get("open");
  if (openScheduleId) openDrawer(openScheduleId);
})();
