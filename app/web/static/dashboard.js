// 일간 점검 대시보드 — /api/dashboard/daily 를 불러와 시스템·모듈별 현황을
// 애니메이션 그래프(라디얼 링·세그먼트 바·카운트업·스태거 진입)로 렌더링한다.
// dashboard.html 이 로드된 페이지에서만 동작하며, 다른 페이지에서는 no-op 이다.

(() => {
  const root = document.querySelector(".dash");
  if (!root) return;

  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const RING_C = 2 * Math.PI * 52; // r=52
  const REFRESH_MS = 30000;

  const TONE_VARS = {
    passed: "var(--st-passed)",
    anomaly: "var(--st-anomaly)",
    error: "var(--st-error)",
    running: "var(--st-running)",
    blocked: "var(--st-blocked)",
    cancelled: "var(--st-blocked)",
    skipped: "var(--st-blocked)",
    waiting_input: "var(--st-running)",
    pending: "var(--st-idle)",
    not_inspected: "var(--st-idle)",
  };
  const toneVar = (tone) => TONE_VARS[tone] || "var(--st-idle)";

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

  // ── 카운트업 애니메이션 ────────────────────────────────────────────────
  function countUp(el, to, { suffix = "" } = {}) {
    const from = Number(el.dataset.value || 0);
    el.dataset.value = String(to);
    if (REDUCED || from === to) {
      el.innerHTML = to + suffix;
      return;
    }
    const dur = 900;
    const start = performance.now();
    const ease = (t) => 1 - Math.pow(1 - t, 3);
    function frame(now) {
      const p = Math.min(1, (now - start) / dur);
      const val = Math.round(from + (to - from) * ease(p));
      el.innerHTML = val + suffix;
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  // ── 라디얼 링 채우기 ──────────────────────────────────────────────────
  function fillRing(circle, pct, tone) {
    circle.setAttribute("class", `dash-ring__value dash-tone-${tone}`);
    const offset = RING_C * (1 - Math.max(0, Math.min(100, pct)) / 100);
    if (REDUCED) {
      circle.style.strokeDashoffset = String(offset);
      return;
    }
    circle.style.strokeDashoffset = String(RING_C);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        circle.style.strokeDashoffset = String(offset);
      });
    });
  }

  // 시스템 건강 톤(우선순위: 실패 > 이상 > 진행 > 정상 > 미점검)
  function systemTone(sys) {
    const c = sys.counts;
    if (sys.module_total === 0 || c.not_inspected === sys.module_total) return "not_inspected";
    if (c.error > 0) return "error";
    if (c.anomaly > 0) return "anomaly";
    if (c.running > 0) return "running";
    if (c.passed > 0) return "passed";
    return "not_inspected";
  }

  function pill(el, label, tone) {
    el.textContent = label;
    el.style.color = toneVar(tone);
    el.style.backgroundColor = `color-mix(in srgb, ${toneVar(tone)} 14%, white)`;
  }

  function fmtTime(iso) {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
    } catch {
      return null;
    }
  }

  const TRIGGER_LABEL = { schedule: "예약", manual: "수동", suite: "전체점검" };

  // ── 세그먼트 바 ───────────────────────────────────────────────────────
  const SEG_ORDER = [
    ["passed", "passed"],
    ["running", "running"],
    ["anomaly", "anomaly"],
    ["error", "error"],
    ["other", "blocked"],
    ["not_inspected", "not_inspected"],
  ];
  function buildSegbar(container, sys) {
    container.innerHTML = "";
    const total = sys.module_total || 1;
    SEG_ORDER.forEach(([key, tone], i) => {
      const n = sys.counts[key] || 0;
      if (n === 0) return;
      const seg = document.createElement("div");
      seg.className = "dash-seg";
      seg.style.width = `${(n / total) * 100}%`;
      seg.style.backgroundColor = toneVar(tone);
      seg.style.transitionDelay = `${i * 70}ms`;
      seg.title = `${n}개`;
      container.appendChild(seg);
    });
  }

  const COUNT_ROWS = [
    ["정상", "passed", "passed"],
    ["이상징후", "anomaly", "anomaly"],
    ["점검실패", "error", "error"],
    ["미점검", "not_inspected", "not_inspected"],
  ];
  function buildCounts(container, sys) {
    container.innerHTML = "";
    for (const [label, key, tone] of COUNT_ROWS) {
      const row = document.createElement("div");
      row.className = "inline-flex items-center gap-1.5";
      row.innerHTML =
        `<span class="h-2 w-2 rounded-full" style="background:${toneVar(tone)}"></span>` +
        `<span class="text-gray-500">${label}</span>` +
        `<span class="ml-auto font-semibold text-gray-800" style="font-variant-numeric:tabular-nums">${sys.counts[key] || 0}</span>`;
      container.appendChild(row);
    }
  }

  // ── 모듈 칩 ───────────────────────────────────────────────────────────
  function buildModules(container, sys) {
    container.innerHTML = "";
    for (const m of sys.modules) {
      const chip = document.createElement("span");
      chip.className =
        `dash-chip dash-chip--${m.tone} inline-flex items-center gap-1.5 rounded-md bg-gray-50 px-2 py-1 ` +
        "text-[11px] font-medium text-gray-600 ring-1 ring-gray-100";
      chip.title = `${m.name} · ${m.status_label}`;
      const dot = document.createElement("span");
      dot.className = `dash-chip__dot h-2 w-2 rounded-full dash-tone-${m.tone}`;
      dot.style.backgroundColor = toneVar(m.tone);
      const name = document.createElement("span");
      name.className = "truncate max-w-[9rem]";
      name.textContent = m.name;
      chip.append(dot, name);
      container.appendChild(chip);
    }
  }

  // ── 시스템 카드 ───────────────────────────────────────────────────────
  function buildSystemCard(sys) {
    const tpl = $("#dash-system-template");
    const node = tpl.content.firstElementChild.cloneNode(true);

    $('[data-field="name"]', node).textContent = sys.system_name;

    const latestEl = $('[data-field="latest"]', node);
    const time = fmtTime(sys.latest_run_at);
    if (time) {
      const trg = TRIGGER_LABEL[sys.triggered_by] || sys.triggered_by || "";
      latestEl.textContent = `최근 점검 ${time}${trg ? ` · ${trg}` : ""}`;
    } else {
      latestEl.textContent = "오늘 점검 이력 없음";
    }

    pill($('[data-field="status-pill"]', node), sys.latest_run_status_label, sys.latest_run_tone);

    buildSegbar($('[data-field="segbar"]', node), sys);
    buildCounts($('[data-field="counts"]', node), sys);
    buildModules($('[data-field="modules"]', node), sys);

    if (sys.latest_run_id) {
      node.style.cursor = "pointer";
      node.addEventListener("click", (e) => {
        if (e.target.closest("a")) return;
        window.location.href = `/runs/${sys.latest_run_id}`;
      });
    }

    // 카드 노출 시 채울 값 저장
    node._activate = () => {
      fillRing($('[data-field="ring"]', node), sys.pass_rate, systemTone(sys));
      countUp($('[data-field="rate"]', node), sys.pass_rate, {
        suffix: '<span class="text-[10px] text-gray-400">%</span>',
      });
      $$(".dash-seg", node).forEach((s) => s.classList.add("is-in"));
    };
    return node;
  }

  // ── 진입 애니메이션(스태거 + 활성화) ──────────────────────────────────
  let observer = null;
  function revealAll(cards) {
    if (observer) observer.disconnect();
    if (REDUCED || !("IntersectionObserver" in window)) {
      cards.forEach((c) => {
        c.classList.add("is-in");
        c._activate && c._activate();
      });
      return;
    }
    let order = 0;
    observer = new IntersectionObserver(
      (entries, obs) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const c = entry.target;
          c.style.transitionDelay = `${(order++ % 6) * 80}ms`;
          c.classList.add("is-in");
          c._activate && c._activate();
          obs.unobserve(c);
        }
      },
      { threshold: 0.15 }
    );
    cards.forEach((c) => observer.observe(c));
  }

  // ── 렌더 ──────────────────────────────────────────────────────────────
  function renderHero(totals) {
    const rate = totals.pass_rate || 0;
    fillRing($("#dash-hero-ring"), rate, heroTone(totals));
    countUp($("#dash-hero-rate"), rate, {
      suffix: '<span class="text-lg text-gray-400">%</span>',
    });
    const caption = $("#dash-hero-caption");
    caption.textContent =
      `${totals.modules}개 모듈 중 ${totals.passed}개 정상` +
      (totals.not_inspected ? ` · ${totals.not_inspected}개 미점검` : "");
  }

  function heroTone(totals) {
    if (!totals.modules || totals.not_inspected === totals.modules) return "not_inspected";
    if (totals.error > 0) return "error";
    if (totals.anomaly > 0) return "anomaly";
    if (totals.running > 0) return "running";
    if (totals.passed > 0) return "passed";
    return "not_inspected";
  }

  function renderKpis(totals) {
    $$("[data-kpi]").forEach((el) => {
      const key = el.dataset.kpi;
      if (key in totals) countUp(el, totals[key]);
    });
  }

  function render(data) {
    $("#dash-date").textContent = data.date_label || "";
    renderHero(data.totals);
    renderKpis(data.totals);

    const container = $("#dash-systems");
    container.innerHTML = "";
    $("#dash-empty").classList.toggle("hidden", data.systems.length > 0);

    const cards = [];
    for (const sys of data.systems) {
      const card = buildSystemCard(sys);
      container.appendChild(card);
      cards.push(card);
    }

    // 상단 요약 카드는 즉시 노출/활성화(위쪽 고정)
    const topCards = $$(".dash-reveal", root).filter((c) => !cards.includes(c));
    requestAnimationFrame(() => topCards.forEach((c) => c.classList.add("is-in")));

    revealAll(cards);
  }

  // ── 데이터 로드 ───────────────────────────────────────────────────────
  let refreshTimer = null;
  async function load() {
    try {
      const res = await fetch("/api/dashboard/daily", { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      $("#dash-error").classList.add("hidden");
      render(data);
    } catch (err) {
      console.error("일간 점검 현황 로드 실패", err);
      $("#dash-error").classList.remove("hidden");
    }
  }

  $("#dash-refresh")?.addEventListener("click", () => {
    const btn = $("#dash-refresh");
    btn.disabled = true;
    load().finally(() => {
      setTimeout(() => (btn.disabled = false), 600);
    });
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (refreshTimer) clearInterval(refreshTimer);
      refreshTimer = null;
    } else if (!refreshTimer) {
      refreshTimer = setInterval(load, REFRESH_MS);
      load();
    }
  });

  load();
  refreshTimer = setInterval(load, REFRESH_MS);
})();
