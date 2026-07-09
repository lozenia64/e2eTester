// 시스템 인사이트 — 시스템 선택기 + 3 탭(헬스/타임라인/모듈 딥다이브).
// 각 탭은 지연 로드되며, 서버가 만든 Plotly figure JSON 을 Plotly.js 로 렌더한다.
// insights.html 이 로드된 페이지에서만 동작한다(다른 페이지에서는 no-op).

(() => {
  const root = document.querySelector(".insight");
  if (!root) return;

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const RING_C = 2 * Math.PI * 52;
  const PLOTLY_CONFIG = { displayModeBar: false, responsive: true, locale: "ko" };
  const TABS = ["health", "timeline", "modules"];

  const state = {
    system: $("#insight-system")?.value || root.dataset.selected || "",
    tab: "health",
    cache: {}, // { [system]: { health, timeline, breakdown } }
    compare: [],
  };

  // ── 포맷 유틸 ────────────────────────────────────────────────────────────
  const fmtDur = (ms) => {
    if (ms == null) return "–";
    const s = ms / 1000;
    if (s < 60) return `${s.toFixed(1)}초`;
    const m = Math.floor(s / 60);
    return `${m}분 ${Math.round(s % 60)}초`;
  };
  const relTime = (iso) => {
    if (!iso) return "–";
    const diff = Date.now() - new Date(iso).getTime();
    const min = Math.floor(diff / 60000);
    if (min < 1) return "방금";
    if (min < 60) return `${min}분 전`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}시간 전`;
    const day = Math.floor(hr / 24);
    if (day < 30) return `${day}일 전`;
    const mo = Math.floor(day / 30);
    return `${mo}개월 전`;
  };
  const absTime = (iso) =>
    iso ? new Date(iso).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
  const rateTone = (r) => (r == null ? "not_inspected" : r >= 95 ? "passed" : r >= 80 ? "anomaly" : "error");

  function plot(id, figure) {
    const el = document.getElementById(id);
    if (!el || typeof Plotly === "undefined" || !figure) return;
    Plotly.react(el, figure.data || [], { ...figure.layout, autosize: true }, PLOTLY_CONFIG);
  }
  function resizeIn(container) {
    if (typeof Plotly === "undefined") return;
    $$(".js-plotly-plot", container).forEach((el) => Plotly.Plots.resize(el));
  }

  // ── 데이터 로드(탭별 지연) ────────────────────────────────────────────────
  async function fetchJSON(url) {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }
  function bucket() {
    return (state.cache[state.system] ||= {});
  }
  async function ensure(tab) {
    const b = bucket();
    if (tab === "health" && !b.health) b.health = await fetchJSON(`/api/systems/${state.system}/health?days=30`);
    if (tab === "timeline" && !b.timeline) b.timeline = await fetchJSON(`/api/systems/${state.system}/timeline?limit=50`);
    if (tab === "modules" && !b.breakdown) b.breakdown = await fetchJSON(`/api/systems/${state.system}/modules/breakdown`);
  }

  async function loadTab(tab) {
    if (!state.system) return;
    $("#insight-error").classList.add("hidden");
    try {
      await ensure(tab);
      if (tab === "health") renderHealth(bucket().health);
      if (tab === "timeline") renderTimeline(bucket().timeline);
      if (tab === "modules") renderModules(bucket().breakdown);
    } catch (_) {
      $("#insight-error").classList.remove("hidden");
    }
  }

  // ── 헬스 렌더 ────────────────────────────────────────────────────────────
  function renderHealth(data) {
    const h = data.header;
    $("#health-days").textContent = data.days;
    const score = h.score;
    const ring = $("#health-ring");
    ring.className = `insight-ring__value insight-tone-${h.score_tone}`;
    ring.setAttribute("stroke-dashoffset", RING_C * (1 - (score || 0) / 100));
    $("#health-score").textContent = score == null ? "–" : `${score}%`;
    $("#health-streak").textContent = h.streak;
    $("#health-headline").textContent =
      score == null ? "아직 점검 데이터가 없습니다." : score >= 95 ? "안정적으로 운영 중입니다." : score >= 80 ? "간헐적 이상이 관찰됩니다." : "주의가 필요합니다.";
    $("#health-last-anomaly").textContent = h.last_anomaly_at ? relTime(h.last_anomaly_at) : "이상 없음 ✨";
    $("#health-avg-duration").textContent = fmtDur(h.avg_duration_ms);
    const delta = $("#health-duration-delta");
    if (h.duration_delta_pct == null) {
      delta.textContent = "";
    } else if (h.duration_delta_pct === 0) {
      delta.textContent = "전주와 동일";
      delta.className = "text-xs font-semibold text-gray-400";
    } else {
      const up = h.duration_delta_pct > 0;
      delta.textContent = `${up ? "▲" : "▼"} ${Math.abs(h.duration_delta_pct)}%`;
      delta.className = `text-xs font-semibold ${up ? "text-red-600" : "text-green-600"}`;
    }

    // 안정성 랭킹 표
    const tbody = $("#health-stability");
    tbody.innerHTML = "";
    if (!data.stability.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="py-6 text-center text-xs text-gray-400">데이터 없음</td></tr>';
    }
    for (const m of data.stability) {
      const tr = document.createElement("tr");
      tr.className = "border-b border-gray-50";
      tr.innerHTML = `
        <td class="py-2 font-medium text-gray-800">${esc(m.name)}</td>
        <td class="py-2 text-center"><span class="${m.flaky_score > 0 ? "font-bold text-amber-600" : "text-gray-400"}">${m.flaky_score}</span></td>
        <td class="py-2 text-right insight-tone-${rateTone(m.pass_rate)}">${m.pass_rate == null ? "–" : m.pass_rate + "%"}</td>
        <td class="py-2 text-right text-gray-500">${fmtDur(m.avg_duration_ms)}</td>
        <td class="py-2 text-right"><span class="inline-block h-2.5 w-2.5 rounded-full insight-bg-${m.last_status_tone}" title="${esc(m.last_status_label)}"></span></td>`;
      tbody.appendChild(tr);
    }

    plot("insight-health-trend", data.charts?.["insight-health-trend"]);
    plot("insight-health-calendar", data.charts?.["insight-health-calendar"]);
    revealIn($("#tab-health"));
  }

  // ── 타임라인 렌더 ────────────────────────────────────────────────────────
  const PILL = {
    passed: "bg-green-100 text-green-700",
    anomaly: "bg-amber-100 text-amber-700",
    error: "bg-red-100 text-red-700",
    running: "bg-blue-100 text-blue-700",
    waiting_input: "bg-blue-100 text-blue-700",
    cancelled: "bg-gray-100 text-gray-500",
    pending: "bg-gray-100 text-gray-500",
    not_inspected: "bg-gray-100 text-gray-400",
  };
  const pillClass = (tone) => PILL[tone] || "bg-gray-100 text-gray-600";

  function renderTimeline(data) {
    state.compare = [];
    updateCompareBar();
    $("#timeline-compare-result").classList.add("hidden");
    const list = $("#timeline-list");
    list.innerHTML = "";
    $("#timeline-empty").classList.toggle("hidden", data.cards.length > 0);

    const tpl = $("#timeline-card-template");
    for (const card of data.cards) {
      const node = tpl.content.firstElementChild.cloneNode(true);
      hydrateCard(node, card);
      list.appendChild(node);
    }
  }

  function chip(text, kind) {
    const cls = kind === "recovered" ? "bg-green-50 text-green-700" : kind === "failed" ? "bg-red-50 text-red-700" : "bg-gray-100 text-gray-500";
    return `<span class="rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}">${esc(text)}</span>`;
  }

  function hydrateCard(node, card) {
    const pill = $('[data-field="status-pill"]', node);
    pill.textContent = card.status_label;
    pill.className = `rounded-full px-2 py-0.5 text-[11px] font-bold ${pillClass(card.status_tone)}`;

    if (card.regression_modules.length) {
      const reg = $('[data-field="regression"]', node);
      reg.classList.remove("hidden");
      reg.classList.add("inline-flex");
      $('[data-field="regression-text"]', reg).textContent =
        card.regression_modules.map((m) => m.name).join(", ") + " 회귀";
    }

    $('[data-field="trigger"]', node).textContent = card.trigger_label;
    $('[data-field="executor"]', node).textContent = card.executor;
    $('[data-field="when"]', node).textContent = absTime(card.requested_at);
    const link = $('[data-field="run-link"]', node);
    link.textContent = card.run_id;
    link.href = `/runs/${card.run_id}`;
    $('[data-field="duration"]', node).textContent = fmtDur(card.duration_ms);

    const chips = $('[data-field="chips"]', node);
    chips.innerHTML =
      card.recovered.map((m) => chip("↑ " + m.name, "recovered")).join("") +
      card.newly_failed.map((m) => chip("↓ " + m.name, "failed")).join("");

    // 상세(펼침)
    const expand = $('[data-field="expand"]', node);
    const detail = $('[data-field="detail"]', node);
    if (card.is_anomaly && card.failed_modules.length) {
      expand.classList.remove("hidden");
      expand.addEventListener("click", () => {
        const open = detail.classList.toggle("hidden");
        expand.textContent = open ? "상세 ▾" : "접기 ▴";
        if (!detail.dataset.built) {
          detail.innerHTML = card.failed_modules.map(renderFailedModule).join("");
          detail.dataset.built = "1";
        }
      });
    }

    // 비교 체크박스
    const cb = $('[data-field="compare"]', node);
    cb.__card = card;
    cb.addEventListener("change", () => onCompareToggle(card, cb));
  }

  function renderFailedModule(m) {
    const shot = m.screenshot
      ? `<a href="${m.screenshot}" target="_blank" rel="noreferrer" class="block h-24 w-36 shrink-0 overflow-hidden rounded-lg ring-1 ring-gray-100"><img src="${m.screenshot}" class="h-full w-full object-cover" alt="종료 화면"></a>`
      : "";
    return `
      <div class="flex gap-3 rounded-lg bg-gray-50 p-3">
        ${shot}
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="rounded-full px-2 py-0.5 text-[11px] font-bold ${pillClass(m.tone)}">${esc(m.status_label)}</span>
            <span class="text-sm font-semibold text-gray-800">${esc(m.name)}</span>
          </div>
          <p class="mt-1 text-xs text-gray-600">${esc(m.ai_summary || m.message || "요약 없음")}</p>
          ${m.ai_action ? `<p class="mt-1 text-[11px] text-indigo-600">→ ${esc(m.ai_action)}</p>` : ""}
          ${m.current_url ? `<p class="mt-1 truncate text-[11px] text-gray-400">${esc(m.current_url)}</p>` : ""}
        </div>
      </div>`;
  }

  // ── 두 Run 비교 ──────────────────────────────────────────────────────────
  function onCompareToggle(card, cb) {
    if (cb.checked) {
      state.compare.push(card);
      // 최대 2개만 유지 — 오래된 선택을 자동 해제한다.
      while (state.compare.length > 2) {
        const dropped = state.compare.shift();
        const el = $$('#timeline-list [data-field="compare"]').find((c) => c.__card === dropped);
        if (el) el.checked = false;
      }
    } else {
      state.compare = state.compare.filter((c) => c !== card);
    }
    updateCompareBar();
  }

  function updateCompareBar() {
    const bar = $("#timeline-compare-bar");
    const show = state.compare.length === 2;
    bar.classList.toggle("hidden", !show);
    bar.classList.toggle("flex", show);
  }

  function renderCompare() {
    const [a, b] = state.compare;
    if (!a || !b) return;
    const fails = (c) => new Set(c.failed_modules.map((m) => m.module_id));
    const fa = fails(a);
    const fb = fails(b);
    const names = {};
    [...a.failed_modules, ...b.failed_modules].forEach((m) => (names[m.module_id] = m.name));
    const allIds = new Set([...fa, ...fb]);
    const rows = [...allIds]
      .map((id) => {
        const inA = fa.has(id);
        const inB = fb.has(id);
        const diff = inA !== inB;
        return `<tr class="${diff ? "bg-amber-50" : ""}">
          <td class="py-1.5 pr-3 font-medium text-gray-700">${esc(names[id])}</td>
          <td class="py-1.5 text-center">${inA ? "❌" : "✅"}</td>
          <td class="py-1.5 text-center">${inB ? "❌" : "✅"}</td>
        </tr>`;
      })
      .join("");
    const col = (c) => `<div><p class="text-xs text-gray-400">${absTime(c.requested_at)}</p>
      <a href="/runs/${c.run_id}" class="text-sm font-bold text-indigo-600 hover:underline">${esc(c.run_id)}</a>
      <span class="ml-1 rounded-full px-2 py-0.5 text-[11px] font-bold ${pillClass(c.status_tone)}">${esc(c.status_label)}</span></div>`;
    const box = $("#timeline-compare-result");
    box.innerHTML = `
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-bold text-gray-900">두 Run 비교</h3>
        <button id="cmp-close" class="text-xs text-gray-400 hover:text-gray-700">닫기</button>
      </div>
      <div class="mt-3 grid grid-cols-2 gap-4">${col(a)}${col(b)}</div>
      <table class="mt-4 w-full text-sm">
        <thead><tr class="border-b border-gray-100 text-[11px] uppercase text-gray-400">
          <th class="py-1.5 text-left">모듈</th><th class="py-1.5 text-center">${esc(a.run_id)}</th><th class="py-1.5 text-center">${esc(b.run_id)}</th>
        </tr></thead>
        <tbody>${rows || '<tr><td colspan="3" class="py-3 text-center text-xs text-gray-400">두 Run 모두 실패 모듈이 없습니다.</td></tr>'}</tbody>
      </table>`;
    box.classList.remove("hidden");
    $("#cmp-close", box).addEventListener("click", () => box.classList.add("hidden"));
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // ── 모듈 딥다이브 렌더 ────────────────────────────────────────────────────
  function computeLevels(modules) {
    const byId = Object.fromEntries(modules.map((m) => [m.module_id, m]));
    const memo = {};
    const level = (id, seen = new Set()) => {
      if (memo[id] != null) return memo[id];
      if (seen.has(id)) return 0;
      seen.add(id);
      const m = byId[id];
      const deps = (m?.depends_on || []).filter((d) => byId[d]);
      const lv = deps.length ? 1 + Math.max(...deps.map((d) => level(d, seen))) : 0;
      memo[id] = lv;
      return lv;
    };
    modules.forEach((m) => level(m.module_id));
    return memo;
  }

  function renderModules(data) {
    const cols = $('[data-role="flow-cols"]');
    cols.innerHTML = "";
    const levels = computeLevels(data.modules);
    const maxLevel = Math.max(0, ...Object.values(levels));
    const byLevel = Array.from({ length: maxLevel + 1 }, () => []);
    data.modules.forEach((m) => byLevel[levels[m.module_id]].push(m));

    byLevel.forEach((group) => {
      const col = document.createElement("div");
      col.className = "flow-col";
      group
        .sort((a, b) => a.order - b.order)
        .forEach((m) => col.appendChild(makeNode(m)));
      cols.appendChild(col);
    });

    requestAnimationFrame(() => drawEdges(data.modules));
    // 첫 노드 자동 선택
    if (data.modules.length) selectNode(data.modules[0], data);
    plot("insight-cumulative", data.charts?.["insight-cumulative"]);
    revealIn($("#tab-modules"));
    // 노드 클릭 위임
    cols.onclick = (e) => {
      const btn = e.target.closest(".flow-node");
      if (!btn) return;
      const m = data.modules.find((x) => x.module_id === btn.dataset.moduleId);
      if (m) selectNode(m, data);
    };
  }

  function makeNode(m) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "flow-node";
    btn.dataset.moduleId = m.module_id;
    btn.dataset.slowing = String(!!m.is_slowing);
    btn.dataset.flaky = String(!!m.is_flaky);
    btn.setAttribute("aria-pressed", "false");
    const badges =
      (m.is_slowing ? `<span class="flow-badge bg-red-50 text-red-600" title="과거 대비 느려짐">느려짐 +${m.slowdown_pct}%</span>` : "") +
      (m.is_flaky ? '<span class="flow-badge bg-amber-50 text-amber-600">flaky</span>' : "");
    btn.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="flow-badge bg-gray-100 text-gray-500">#${m.order}</span>
        <span class="h-2 w-2 rounded-full insight-bg-${m.last_status_tone}" title="${esc(m.last_status_label)}"></span>
      </div>
      <p class="mt-1.5 truncate text-sm font-bold text-gray-900">${esc(m.name)}</p>
      <div class="mt-1 flex items-center justify-between text-[11px] text-gray-400">
        <span>통과율 <b class="insight-tone-${rateTone(m.pass_rate)}">${m.pass_rate == null ? "–" : m.pass_rate + "%"}</b></span>
        <span>${fmtDur(m.avg_duration_ms)}</span>
      </div>
      ${badges ? `<div class="mt-2 flex gap-1">${badges}</div>` : ""}`;
    return btn;
  }

  function drawEdges(modules) {
    const wrap = $(".flow-wrap");
    const svg = $('[data-role="flow-edges"]');
    if (!wrap || !svg) return;
    const wrapRect = wrap.getBoundingClientRect();
    const W = wrap.scrollWidth;
    const H = wrap.clientHeight;
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";
    const nodeRect = (id) => {
      const el = $(`.flow-node[data-module-id="${CSS.escape(id)}"]`);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {
        left: r.left - wrapRect.left + wrap.scrollLeft,
        right: r.right - wrapRect.left + wrap.scrollLeft,
        cy: r.top - wrapRect.top + r.height / 2,
      };
    };
    for (const m of modules) {
      const to = nodeRect(m.module_id);
      if (!to) continue;
      for (const depId of m.depends_on || []) {
        const from = nodeRect(depId);
        if (!from) continue;
        const x1 = from.right;
        const y1 = from.cy;
        const x2 = to.left;
        const y2 = to.cy;
        const mx = (x1 + x2) / 2;
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("class", "flow-edge");
        path.setAttribute("d", `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
        svg.appendChild(path);
      }
    }
  }

  function selectNode(m, data) {
    $$(".flow-node").forEach((n) => n.setAttribute("aria-pressed", String(n.dataset.moduleId === m.module_id)));
    const panel = $("#insight-deepdive");
    panel.classList.remove("hidden");
    $("#dd-title").textContent = m.name;
    const slowdownStat =
      m.slowdown_pct == null
        ? null
        : `과거대비 <b class="${m.slowdown_pct > 0 ? "text-red-600" : "text-green-600"}">${m.slowdown_pct > 0 ? "+" : ""}${m.slowdown_pct}%</b>`;
    $("#dd-stats").innerHTML = [
      `통과율 <b class="insight-tone-${rateTone(m.pass_rate)}">${m.pass_rate == null ? "–" : m.pass_rate + "%"}</b>`,
      `평균소요 <b class="text-gray-700">${fmtDur(m.avg_duration_ms)}</b>`,
      ...(slowdownStat ? [slowdownStat] : []),
      `flaky <b class="${m.flaky_score > 0 ? "text-amber-600" : "text-gray-500"}">${m.flaky_score}</b>`,
      `실행 <b class="text-gray-700">${m.runs_count}</b>회`,
    ]
      .map((s) => `<span>${s}</span>`)
      .join("");

    plot("insight-dd-sparkline", m.charts?.sparkline);
    plot("insight-dd-donut", m.charts?.donut);

    const shots = $("#dd-shots");
    shots.innerHTML = "";
    if (!m.screenshots.length) {
      shots.innerHTML = '<p class="py-4 text-xs text-gray-400">스크린샷 없음</p>';
    }
    for (const s of m.screenshots) {
      const a = document.createElement("a");
      a.href = s.url;
      a.target = "_blank";
      a.rel = "noreferrer";
      a.className = "relative block h-24 w-36 shrink-0 overflow-hidden rounded-lg ring-1 ring-gray-100";
      a.innerHTML = `<img src="${s.url}" class="h-full w-full object-cover" alt="실행 화면" loading="lazy">
        <span class="absolute bottom-1 left-1 rounded bg-black/55 px-1 py-0.5 text-[10px] text-white">${absTime(s.at)}</span>`;
      shots.appendChild(a);
    }
    resizeIn(panel);
  }

  // ── reveal 애니메이션 ─────────────────────────────────────────────────────
  function revealIn(container) {
    $$(".insight-reveal", container).forEach((el, i) =>
      requestAnimationFrame(() => setTimeout(() => el.classList.add("is-in"), i * 40)),
    );
  }

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  // ── 탭 전환 ──────────────────────────────────────────────────────────────
  function switchTab(tab, { push = true } = {}) {
    if (!TABS.includes(tab)) tab = "health";
    state.tab = tab;
    $$(".insight-tab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
    TABS.forEach((t) => $(`#tab-${t}`).classList.toggle("hidden", t !== tab));
    if (push) history.replaceState(null, "", `#${tab}`);
    loadTab(tab).then(() => resizeIn($(`#tab-${tab}`)));
  }

  $$(".insight-tab").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  $("#insight-system")?.addEventListener("change", (e) => {
    state.system = e.target.value;
    history.replaceState(null, "", `/systems/${state.system}/insights#${state.tab}`);
    // 캐시 무시하고 현재 탭 재로드
    loadTab(state.tab).then(() => resizeIn($(`#tab-${state.tab}`)));
  });
  $("#insight-refresh")?.addEventListener("click", () => {
    delete state.cache[state.system];
    loadTab(state.tab);
  });
  $("#timeline-compare-go")?.addEventListener("click", renderCompare);
  $("#timeline-compare-clear")?.addEventListener("click", () => {
    state.compare = [];
    $$('#timeline-list [data-field="compare"]').forEach((cb) => (cb.checked = false));
    updateCompareBar();
    $("#timeline-compare-result").classList.add("hidden");
  });

  window.addEventListener("resize", () => resizeIn($(`#tab-${state.tab}`)));

  // 초기 탭 = URL 해시
  const initial = (location.hash || "").replace("#", "");
  switchTab(TABS.includes(initial) ? initial : "health", { push: false });
})();
