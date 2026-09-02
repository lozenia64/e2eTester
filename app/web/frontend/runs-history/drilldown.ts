/** 격자 셀 드릴다운 — 그 날 그 시스템의 Run 목록.
 *
 *  셀에 실린 대표 run_id 를 쓰지 않는다(설계 D4). 서버가 슬롯당 한 건으로
 *  접기 때문에 재실행 이력이 숨는다. 별도 조회로 전량을 가져온다. */

import { formatRunTime } from "./format";

export type DayRun = {
  run_id: string;
  status: string;
  status_label: string;
  requested_at: string;
  module_total: number;
  module_passed: number;
  suite_id: string | null;
};

export function renderDrilldown(
  panel: HTMLElement,
  systemName: string,
  dayKey: string,
  runs: DayRun[],
): void {
  panel.replaceChildren();

  const head = document.createElement("p");
  head.className = "rhist-drill__head";
  head.textContent = `${dayKey} · ${systemName}`;
  panel.appendChild(head);

  if (runs.length === 0) {
    const empty = document.createElement("p");
    empty.className = "rhist-drill__empty";
    empty.textContent = "이 날 실행된 Run 이 없습니다.";
    panel.appendChild(empty);
    return;
  }

  for (const item of runs) {
    const row = document.createElement("div");
    row.className = "rhist-drill__row";
    row.dataset.tone = item.status;

    const time = document.createElement("span");
    time.textContent = formatRunTime(item.requested_at);

    const status = document.createElement("span");
    status.textContent = item.status_label;

    const modules = document.createElement("span");
    modules.textContent = `모듈 ${item.module_passed}/${item.module_total}`;

    const link = document.createElement("a");
    link.href = `/runs/${item.run_id}`;
    link.textContent = "Run 상세 →";

    row.append(time, status, modules, link);
    panel.appendChild(row);
  }
}

export function renderDrilldownError(panel: HTMLElement): void {
  panel.replaceChildren();
  const message = document.createElement("p");
  message.className = "rhist-drill__empty";
  message.textContent = "Run 목록을 불러오지 못했습니다.";
  panel.appendChild(message);
}

export function bindDrilldown(
  grid: HTMLElement,
  panel: HTMLElement,
  nameOf: (systemCode: string) => string,
): void {
  grid.addEventListener("click", (event) => {
    const cell = (event.target as HTMLElement | null)?.closest<HTMLElement>(".rhist-cell");
    if (!cell || !grid.contains(cell)) {
      return;
    }
    const { day, system } = cell.dataset;
    if (!day || !system) {
      return;
    }

    for (const selected of grid.querySelectorAll<HTMLElement>('[data-selected="true"]')) {
      delete selected.dataset.selected;
    }
    cell.dataset.selected = "true";

    void loadDay(panel, system, day, nameOf(system));
  });
}

async function loadDay(
  panel: HTMLElement,
  systemCode: string,
  dayKey: string,
  systemName: string,
): Promise<void> {
  try {
    const params = new URLSearchParams({ system_code: systemCode, day: dayKey });
    const response = await fetch(`/api/runs/day?${params.toString()}`);
    if (!response.ok) {
      renderDrilldownError(panel);
      return;
    }
    renderDrilldown(panel, systemName, dayKey, (await response.json()) as DayRun[]);
  } catch {
    // 격자는 이미 그려져 있다 — 실패는 패널 안에서만 말한다(설계 §3.3).
    renderDrilldownError(panel);
  }
}
