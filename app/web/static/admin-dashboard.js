// 관리자 관제 대시보드 — /admin 전용 (7일×3타임 커버리지 + 오늘 모듈 현황)
(() => {
  const root = document.getElementById("admin-dashboard-root");
  if (!root) return;

  const REFRESH_MS = 30000;
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const SLOTS_PER_DAY = 3;

  const TONE_VARS = {
    passed: "var(--st-passed)",
    anomaly: "var(--st-anomaly)",
    error: "var(--st-error)",
    running: "var(--st-running)",
    blocked: "var(--st-blocked)",
    cancelled: "var(--st-cancelled)",
    skipped: "var(--st-blocked)",
    waiting_input: "var(--st-running)",
    pending: "var(--st-idle)",
    not_inspected: "var(--st-idle)",
    not_checked: "var(--st-idle)",
  };
  const toneVar = (tone) => TONE_VARS[tone] || "var(--st-idle)";

  const SLOT_META = {
    day: { label: "주간", title: "주간 06:00–18:00" },
    evening: { label: "저녁", title: "저녁 18:00–22:00" },
    night: { label: "야간", title: "야간 22:00–06:00" },
  };

  const SLOT_ICON = {
    day: `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path stroke-linecap="round" d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>`,
    evening: `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M17 18a5 5 0 10-10 0"/><path stroke-linecap="round" d="M12 2v2M4.22 4.22l1.42 1.42M2 12h2"/></svg>`,
    night: `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>`,
  };

  const SEG_ORDER = [
    ["passed", "passed"],
    ["running", "running"],
    ["anomaly", "anomaly"],
    ["error", "error"],
    ["other", "blocked"],
    ["not_inspected", "not_inspected"],
  ];

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  function esc(text) {
    const el = document.createElement("span");
    el.textContent = text ?? "";
    return el.innerHTML;
  }

  function fmtTime(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString("ko-KR", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "";
    }
  }

  function slotIconHtml(slotId) {
    const meta = SLOT_META[slotId] || { label: slotId, title: slotId };
    const svg = SLOT_ICON[slotId] || "";
    return `<span class="adm-slot-icon" role="img" aria-label="${esc(meta.label)}" title="${esc(meta.title)}">${svg}</span>`;
  }

  function systemDotColor(tone) {
    if (tone === "not_checked") return "var(--st-idle)";
    if (tone === "passed") return "var(--st-passed)";
    return toneVar(tone);
  }

  function revealStagger() {
    if (REDUCED) {
      $$(".adm-reveal").forEach((el) => el.classList.add("is-in"));
      return;
    }
    $$(".adm-reveal").forEach((el, i) => {
      setTimeout(() => el.classList.add("is-in"), 60 + i * 50);
    });
  }

  function renderKpi(totals) {
    $("#kpi-systems").textContent = totals.systems ?? "—";
    $("#kpi-checked").textContent = totals.checked ?? "—";
    $("#kpi-anomaly").textContent = totals.anomaly ?? "—";
    $("#kpi-error").textContent = totals.error ?? "—";
    $("#kpi-all-green").textContent = totals.systems_all_green ?? "—";
  }

  function dayHeaderClass(dowChar) {
    if (dowChar === "토") return " is-sat";
    if (dowChar === "일") return " is-sun";
    return " is-weekday";
  }

  function renderHeatmap(data) {
    const wrap = $("#adm-heatmap");
    const columns = data.columns || [];
    const systems = data.systems || [];
    if (!columns.length || !systems.length) {
      wrap.innerHTML = '<p class="py-8 text-center text-sm text-gray-400">데이터 없음</p>';
      return;
    }

    const dayKeys = [...new Set(columns.map((col) => col.day_key))];

    let html = `<div class="adm-heatmap-grid" role="grid" aria-label="시스템별 7일 점검 커버리지">`;

    html += '<div class="adm-heatmap-grid__label"></div>';
    dayKeys.forEach((dayKey, dayIdx) => {
      const col = columns.find((c) => c.day_key === dayKey);
      const dowChar = col?.label?.split(" ")[0] || "";
      const label = dowChar || dayKey.slice(5);
      const dayStart = dayIdx > 0 ? " is-day-start" : "";
      html += `<div class="adm-heatmap-grid__day${dayHeaderClass(dowChar)}${dayStart}" style="grid-column:span ${SLOTS_PER_DAY}">${esc(label)}</div>`;
    });

    html += '<div class="adm-heatmap-grid__label"></div>';
    columns.forEach((col, idx) => {
      const dayStart = idx > 0 && idx % SLOTS_PER_DAY === 0 ? " is-day-start" : "";
      html += `<div class="adm-heatmap-grid__slot${dayStart}">${slotIconHtml(col.slot_id)}</div>`;
    });

    systems.forEach((sys) => {
      html += `<div class="adm-heatmap-grid__label">
        <span class="adm-sys-dot" style="background:${systemDotColor(sys.latest_tone)}"></span>
        <span class="truncate">${esc(sys.system_name)}</span>
      </div>`;

      (sys.cells || []).forEach((cell, idx) => {
        const title = cell.run_id
          ? `${cell.status_label} · ${fmtTime(cell.checked_at)} · Run 열기`
          : cell.status_label;
        const clickable = cell.run_id ? "1" : "0";
        const tag = cell.run_id ? "button" : "span";
        const dayStart = idx > 0 && idx % SLOTS_PER_DAY === 0 ? " is-day-start" : "";
        const extra = cell.run_id
          ? ` type="button" data-run-id="${esc(cell.run_id)}"`
          : "";
        html += `<div class="adm-heatmap-grid__cell${dayStart}"><${tag} class="adm-cell" data-tone="${esc(cell.tone)}" data-clickable="${clickable}" title="${esc(title)}" aria-label="${esc(sys.system_name)} ${esc(cell.status_label)}"${extra}></${tag}></div>`;
      });
    });

    html += "</div>";
    wrap.innerHTML = html;

    wrap.querySelectorAll("[data-run-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const runId = btn.getAttribute("data-run-id");
        if (runId) window.location.href = `/runs/${encodeURIComponent(runId)}`;
      });
    });
  }

  function buildSegbarHtml(sys) {
    const total = sys.module_total || 1;
    const segments = SEG_ORDER.map(([key, tone]) => {
      const n = (sys.counts || {})[key] || 0;
      if (n === 0) return "";
      return `<div class="adm-seg" style="width:${(n / total) * 100}%;background:${toneVar(tone)}" title="${n}개"></div>`;
    }).join("");
    return `<div class="adm-segbar" role="img" aria-label="모듈 상태 분포">${segments}</div>`;
  }

  function statusPillStyle(tone) {
    const color = tone === "not_checked" ? "#9ca3af" : toneVar(tone);
    return `color:${color};background:color-mix(in srgb, ${color} 12%, white)`;
  }

  function renderDailyCompact(daily) {
    const wrap = $("#adm-daily-compact");
    const systems = daily.systems || [];
    if (!systems.length) {
      wrap.innerHTML = '<p class="py-6 text-center text-sm text-gray-400">오늘 점검 데이터 없음</p>';
      return;
    }

    wrap.innerHTML = `<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">${systems
      .map((sys) => {
        const c = sys.counts || {};
        const tone =
          c.error > 0
            ? "error"
            : c.anomaly > 0
              ? "anomaly"
              : c.running > 0
                ? "running"
                : c.not_inspected === sys.module_total
                  ? "not_checked"
                  : "passed";
        const clickable = sys.latest_run_id ? "1" : "0";
        const modules = (sys.modules || [])
          .map((m) => {
            const dotColor = toneVar(m.tone || "not_inspected");
            return `<span class="adm-chip" title="${esc(m.name)} · ${esc(m.status_label)}">
              <span class="adm-chip__dot" style="background:${dotColor}"></span>
              <span class="truncate max-w-[7rem]">${esc(m.name)}</span>
            </span>`;
          })
          .join("");
        return `<article class="adm-daily-card" data-clickable="${clickable}" data-run-id="${esc(sys.latest_run_id || "")}">
          <div class="flex items-start justify-between gap-2">
            <h3 class="text-sm font-semibold text-gray-900">${esc(sys.system_name)}</h3>
            <span class="adm-status-pill" style="${statusPillStyle(tone)}">${esc(sys.latest_run_status_label || "미점검")}</span>
          </div>
          <p class="mt-1 text-[11px] text-gray-500">모듈 ${sys.inspected}/${sys.module_total} · 통과율 ${sys.pass_rate}%</p>
          <div class="mt-2.5">${buildSegbarHtml(sys)}</div>
          <div class="mt-2.5 flex flex-wrap gap-1">${modules}</div>
        </article>`;
      })
      .join("")}</div>`;

    wrap.querySelectorAll(".adm-daily-card[data-clickable='1']").forEach((card) => {
      card.addEventListener("click", () => {
        const runId = card.getAttribute("data-run-id");
        if (runId) window.location.href = `/runs/${encodeURIComponent(runId)}`;
      });
    });
  }

  async function loadDashboard() {
    try {
      const [coverageRes, dailyRes] = await Promise.all([
        fetch("/api/admin/dashboard"),
        fetch("/api/dashboard/daily"),
      ]);
      if (!coverageRes.ok) throw new Error(`커버리지 로드 실패 (${coverageRes.status})`);
      const coverage = await coverageRes.json();
      renderKpi(coverage.totals || {});
      renderHeatmap(coverage);
      if (coverage.generated_at) {
        $("#adm-updated-at").textContent = `갱신 ${fmtTime(coverage.generated_at)} · 30초`;
      }
      if (dailyRes.ok) {
        const daily = await dailyRes.json();
        renderDailyCompact(daily);
      } else {
        $("#adm-daily-compact").innerHTML =
          '<p class="py-6 text-center text-sm text-gray-400">오늘 모듈 현황을 불러오지 못했습니다.</p>';
      }
      revealStagger();
    } catch (error) {
      $("#adm-heatmap").innerHTML = `<p class="py-8 text-center text-sm text-red-500">${esc(error.message)}</p>`;
      $("#adm-updated-at").textContent = "갱신 실패";
    }
  }

  loadDashboard();
  setInterval(loadDashboard, REFRESH_MS);
})();
