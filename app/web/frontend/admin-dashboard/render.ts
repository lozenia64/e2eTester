import { STATUS_TONES } from "../lib/status.generated";
import { escapeHtml as esc } from "../lib/html";
import { countTo, formatTime as dateLabel, number, replaceContent, setText } from "./dom";
import type { CoverageData, DailyData, PerformanceData } from "./types";

function tone(value: string): string {
  return STATUS_TONES.some(t => t === value) ? value : "pending";
}
function runLink(id: string): string { return `/runs/${encodeURIComponent(id)}`; }

function renderContributions(root: HTMLElement, data: PerformanceData): void {
  const list = root.querySelector("#perf-contribution");
  if (!list) return;
  const max = Math.max(1, ...data.by_system.map(s => s.saved_seconds));
  const active = document.activeElement as HTMLElement | null;
  const existing = new Map(Array.from(list.querySelectorAll<HTMLElement>("[data-system-code]")).map(el => [el.dataset.systemCode, el]));
  const items = data.by_system.map((s, i) => {
    let item = existing.get(s.system_code);
    if (!item) {
      item = document.createElement("li");
      item.className = "perf-bar-row";
      item.dataset.systemCode = s.system_code;
      item.innerHTML = '<div class="perf-bar-label"><a></a><span></span></div><div class="perf-bar-track" aria-hidden="true"><div class="perf-bar-fill"></div></div><span class="perf-bar-detail"></span>';
    }
    const link = item.querySelector("a")!;
    link.textContent = s.system_name;
    link.href = `/admin/runs?system_code=${encodeURIComponent(s.system_code)}`;
    link.dataset.focusKey = `system-${s.system_code}`;
    item.querySelector(".perf-bar-label > span")!.innerHTML = `${number(s.saved_seconds / 3600, 1)}<small>시간</small>`;
    const bar = item.querySelector<HTMLElement>(".perf-bar-fill")!;
    bar.style.setProperty("--bar-width", `${s.saved_seconds / max * 100}%`);
    bar.style.setProperty("--bar-index", String(i));
    item.querySelector(".perf-bar-detail")!.textContent = `${number(s.saved_seconds)}초 · ${number(s.runs)}회 집계`;
    return item;
  });
  if (!items.length) { replaceContent(root, "#perf-contribution", '<li class="perf-empty">등록된 시스템이 없습니다.</li>'); return; }
  delete (list as HTMLElement).dataset.content;
  Array.from(list.children).forEach(child => { if (!items.includes(child as HTMLElement)) child.remove(); });
  items.forEach((item, i) => { if (list.children[i] !== item) list.insertBefore(item, list.children[i] ?? null); });
  if (active && list.contains(active) && document.activeElement !== active) active.focus({ preventScroll: true });
}

export function renderPerformance(root: HTMLElement, data: PerformanceData, first: boolean): void {
  countTo(root, "#perf-saved", data.total_seconds / 3600, first, 1);
  countTo(root, "#perf-runs", data.total_runs, first);
  setText(root, "#perf-month", `${Number(data.period.from.slice(5, 7))}월의 자동 점검 성과`);
  const comparison = data.change_percent === null ? "비교할 전월 실적 없음" :
    `전월 동기간 대비 ${data.change_percent > 0 ? "+" : ""}${number(data.change_percent, 1)}%`;
  setText(root, "#perf-comparison", comparison);
  const badge = root.querySelector<HTMLElement>("#perf-comparison");
  if (badge) badge.dataset.direction = data.change_percent === null ? "none" : data.change_percent < 0 ? "down" : "up";
  setText(root, "#perf-basis-note", data.basis_note);
  setText(root, "#perf-period", `${dateLabel(data.period.from)} ~ ${dateLabel(data.period.to)} · 한국 시간`);
  if (badge) badge.title = `전월 비교 기간 ${dateLabel(data.period.previous_from)} ~ ${dateLabel(data.period.previous_to)}`;
  setText(root, "#perf-saving-note", data.total_seconds > 0 ? `통과 모듈별 수동 점검 기준 시간의 합계 · ${number(data.total_seconds)}초` : "산정 가능한 절감 시간 없음 · 모듈 기준 시간을 확인하세요.");
  renderContributions(root, data);
  const bars = root.querySelector("#perf-contribution");
  if (bars) { bars.classList.toggle("perf-bars-first", first); }
  replaceContent(root, "#perf-trend-table", `<table class="perf-data-table"><caption>일별 절감 시간과 누적 시간 · 단위 초</caption><thead><tr><th scope="col">날짜</th><th scope="col">당일</th><th scope="col">누적</th></tr></thead><tbody>${data.daily.map(day => `<tr><th scope="row">${esc(day.date)}</th><td>${number(day.saved_seconds)}</td><td>${number(day.cumulative_seconds)}</td></tr>`).join("")}</tbody></table>`);
  const lead = data.by_system[0];
  setText(root, "#perf-observation", lead && data.total_seconds > 0 ? `이번 달 추정 절감 시간의 ${number(lead.saved_seconds / data.total_seconds * 100, 1)}%가 ${lead.system_name}에서 나왔습니다. 시스템별 기여도를 참고해 점검 범위를 검토하세요.` : "집계 가능한 성과가 아직 없습니다. 모듈별 수동 점검 기준 시간을 설정하고 자동 점검을 완료하면 성과가 표시됩니다.");
}

export function renderDaily(root: HTMLElement, data: DailyData): void {
  const t = data.totals;
  setText(root, "#perf-today-rate", t.inspected ? `${number(t.pass_rate)}%` : "미점검");
  setText(root, "#perf-today-basis", `${number(t.passed)} / ${number(t.modules)}개 통과 · 전체 모듈 기준`);
  setText(root, "#perf-systems", `${number(t.systems)}개`);
  setText(root, "#perf-attention", `${number(t.anomaly + t.error)}개`);
  setText(root, "#perf-today-date", `${data.date_label} · 당일 최신 모듈 결과`);
  setText(root, "#perf-attention-summary", `오늘 확인할 모듈 ${number(t.anomaly + t.error)}개 · 이상 ${number(t.anomaly)} · 오류 ${number(t.error)}`);
  const attention = data.systems.flatMap(s => s.modules.filter(m => m.tone === "anomaly" || m.tone === "error").map(m => ({ ...m, system_name: s.system_name })));
  replaceContent(root, "#perf-attention-links", attention.length ? attention.map(m => {
    const text = `${m.system_name} · ${m.name} · ${m.status_label}`;
    return m.run_id ? `<a class="perf-attention-link" data-focus-key="attention-${esc(m.module_id)}" href="${runLink(m.run_id)}">${esc(text)}<span aria-hidden="true">↗</span></a>` : `<p>${esc(text)}</p>`;
  }).join("") : `<p class="perf-muted">${t.inspected ? "현재 확인할 이상·오류 모듈이 없습니다." : "아직 오늘의 점검 결과가 없습니다."}</p>`);
  replaceContent(root, "#adm-daily-compact", data.systems.length ? data.systems.map(s => {
    const title = s.latest_run_id ? `<a data-focus-key="daily-${esc(s.system_code)}" href="${runLink(s.latest_run_id)}">${esc(s.system_name)} <span aria-hidden="true">↗</span></a>` : esc(s.system_name);
    return `<article class="perf-system"><div class="perf-system-head"><h3>${title}</h3><span class="perf-state" style="--state-color:var(--st-${tone(s.latest_run_tone)}-text)">${esc(s.latest_run_status_label)}</span></div><p>${number(s.inspected)} / ${number(s.module_total)}개 점검 · 통과율 ${number(s.pass_rate)}%</p><ul class="perf-modules">${s.modules.map(m => {
      const text = `<span class="perf-module-dot" aria-hidden="true" style="--module-color:var(--st-${tone(m.tone)}-solid)"></span>${esc(m.name)}<span class="perf-module-status">${esc(m.status_label)}</span>`;
      return `<li>${m.run_id ? `<a data-focus-key="module-${esc(m.module_id)}" href="${runLink(m.run_id)}">${text}</a>` : `<span>${text}</span>`}</li>`;
    }).join("")}</ul></article>`;
  }).join("") : '<p class="perf-empty">등록된 점검 대상이 없습니다.</p>');
}

export function renderCoverage(root: HTMLElement, data: CoverageData): void {
  const dates = [...new Set(data.columns.map(c => c.day_key))];
  const slots: Record<string, string> = { day: "주간", evening: "저녁", night: "야간" };
  replaceContent(root, "#adm-heatmap", data.systems.length ? `<table class="perf-heatmap"><caption class="sr-only">시스템별 최근 7일 점검 커버리지. 실행 결과가 있는 셀을 누르면 상세 결과로 이동합니다.</caption><thead><tr><th scope="col" rowspan="2">시스템</th>${dates.map(day => `<th scope="colgroup" colspan="${data.columns.filter(c => c.day_key === day).length}">${esc(day.slice(5).replace("-", "."))}</th>`).join("")}</tr><tr>${data.columns.map(c => `<th scope="col" title="${esc(c.label)}">${esc(slots[c.slot_id] || c.slot_id)}</th>`).join("")}</tr></thead><tbody>${data.systems.map(s => `<tr><th scope="row">${esc(s.system_name)}</th>${s.cells.map(cell => {
    const label = `${s.system_name} ${cell.day_key} ${slots[cell.slot_id] || cell.slot_id} ${cell.status_label}`;
    const style = `--cell-color:var(--st-${tone(cell.tone)}-solid)`;
    return `<td>${cell.run_id ? `<a class="perf-cell" data-focus-key="cell-${esc(s.system_code)}-${esc(cell.day_key)}-${esc(cell.slot_id)}" href="${runLink(cell.run_id)}" style="${style}" aria-label="${esc(label)}" title="${esc(label)}"></a>` : `<span class="perf-cell perf-cell-empty" style="${style}" role="img" aria-label="${esc(label)}" title="${esc(label)}"></span>`}</td>`;
  }).join("")}</tr>`).join("")}</tbody></table>` : '<p class="perf-empty">등록된 점검 대상이 없습니다.</p>');
}
