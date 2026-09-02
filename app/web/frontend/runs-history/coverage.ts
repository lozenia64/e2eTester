/** 커버리지 응답(시스템 x 21슬롯) → 화면 격자(시스템 x 7일).
 *
 * 하루를 한 칸으로 접되 슬롯 톤은 조각으로 보존한다(설계 D5). 대표 톤은
 * 2단계다(D6): 3슬롯이 모두 비면 not_checked, 하나라도 돌았으면 돌아간
 * 것들 중 최악. 단순 최악 규칙이면 시스템당 하루 1 Run 인 현 운영에서
 * 정상인 날도 전부 미실행으로 보인다.
 */

export type CoverageCell = {
  day_key: string;
  slot_id: string;
  status: string;
  status_label: string | null;
  tone: string | null;
  run_id: string | null;
  checked_at: string | null;
};

export type CoverageSystem = {
  system_code: string;
  system_name: string;
  cells: CoverageCell[];
};

export type CoverageResponse = {
  window: { day_keys: string[] };
  systems: CoverageSystem[];
};

export type DayCell = { day_key: string; tone: string; slots: string[]; ran: number };
export type GridRow = { system_code: string; system_name: string; days: DayCell[] };

const NOT_CHECKED = "not_checked";

/** 나쁜 것이 먼저 눈에 들어와야 한다 — 앞일수록 나쁘다. */
const SEVERITY = [
  "error",
  "anomaly",
  "waiting_input",
  "running",
  "blocked",
  "cancelled",
  "skipped",
  "passed",
];

function worst(tones: string[]): string {
  for (const tone of SEVERITY) {
    if (tones.includes(tone)) {
      return tone;
    }
  }
  return tones[0] ?? NOT_CHECKED;
}

export function buildGrid(payload: CoverageResponse): GridRow[] {
  const dayKeys = payload.window.day_keys;
  return payload.systems.map((system) => {
    const byDay = new Map<string, CoverageCell[]>();
    for (const cell of system.cells) {
      const bucket = byDay.get(cell.day_key);
      if (bucket) {
        bucket.push(cell);
      } else {
        byDay.set(cell.day_key, [cell]);
      }
    }

    const days = dayKeys.map((dayKey) => {
      const slots = (byDay.get(dayKey) ?? []).map((cell) => cell.tone ?? NOT_CHECKED);
      const ranTones = slots.filter((tone) => tone !== NOT_CHECKED);
      return {
        day_key: dayKey,
        tone: ranTones.length === 0 ? NOT_CHECKED : worst(ranTones),
        slots,
        ran: ranTones.length,
      };
    });

    return { system_code: system.system_code, system_name: system.system_name, days };
  });
}

export function renderGrid(root: HTMLElement, rows: GridRow[], dayKeys: string[]): void {
  root.replaceChildren();
  root.style.setProperty("--rhist-days", String(dayKeys.length));

  const corner = document.createElement("div");
  corner.className = "rhist-grid__corner";
  root.appendChild(corner);

  for (const dayKey of dayKeys) {
    const head = document.createElement("div");
    head.className = "rhist-grid__day";
    head.textContent = dayKey.slice(5).replace("-", "/");
    root.appendChild(head);
  }

  for (const row of rows) {
    const name = document.createElement("div");
    name.className = "rhist-grid__system";
    name.textContent = row.system_name;
    root.appendChild(name);

    for (const day of row.days) {
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "rhist-cell";
      cell.dataset.tone = day.tone;
      cell.dataset.day = day.day_key;
      cell.dataset.system = row.system_code;
      cell.setAttribute(
        "aria-label",
        `${row.system_name} ${day.day_key} ${day.ran === 0 ? "미실행" : `${day.ran}건`}`,
      );

      for (const slotTone of day.slots) {
        const piece = document.createElement("span");
        piece.className = "rhist-cell__slot";
        piece.dataset.tone = slotTone;
        cell.appendChild(piece);
      }

      root.appendChild(cell);
    }
  }
}
