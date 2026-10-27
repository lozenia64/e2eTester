import type { SectionName } from "./types";

const ENDPOINTS: Record<SectionName, string> = {
  performance: "/api/admin/dashboard/performance", daily: "/api/dashboard/daily", coverage: "/api/admin/dashboard",
};
const TITLES: Record<SectionName, string> = { performance: "월간 성과", daily: "오늘 현황", coverage: "7일 커버리지" };

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
}

export class DashboardController {
  private inFlight = false;
  private disposed = false;
  private successes = new Map<SectionName, string>();
  private aborters = new Set<AbortController>();
  private timer: number;
  private refreshButton: HTMLButtonElement | null;
  private visibility = (): void => { if (!document.hidden) void this.refresh(); };
  private manual = (): void => { void this.refresh(); };

  constructor(private root: HTMLElement, private render: (section: SectionName, data: unknown, first: boolean) => void) {
    this.refreshButton = root.querySelector("[data-refresh]");
    this.refreshButton?.addEventListener("click", this.manual);
    document.addEventListener("visibilitychange", this.visibility);
    this.timer = window.setInterval(() => { if (!document.hidden) void this.refresh(); }, 30_000);
  }

  async refresh(): Promise<void> {
    if (this.inFlight || this.disposed) return;
    this.inFlight = true;
    if (this.refreshButton) this.refreshButton.disabled = true;
    await Promise.allSettled((Object.entries(ENDPOINTS) as [SectionName, string][]).map(async ([section, url]) => {
      const status = this.root.querySelector<HTMLElement>(`[data-status="${section}"]`);
      const aborter = new AbortController();
      this.aborters.add(aborter);
      const timeout = window.setTimeout(() => aborter.abort(), 15_000);
      const region = this.root.querySelector<HTMLElement>(`[data-region="${section}"]`);
      region?.setAttribute("aria-busy", "true");
      try {
        const response = await fetch(url, { signal: aborter.signal, headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("조회 실패");
        const payload = await response.json() as { generated_at?: string };
        if (this.disposed) return;
        this.render(section, payload, !this.successes.has(section));
        const stamp = payload.generated_at || new Date().toISOString();
        this.successes.set(section, stamp);
        if (status) { status.textContent = `마지막 갱신 ${formatTime(stamp)}`; delete status.dataset.failed; }
      } catch {
        if (this.disposed) return;
        if (status) {
          const previous = this.successes.get(section);
          status.textContent = previous ? `갱신 실패 · 마지막 성공 ${formatTime(previous)} · 새로고침으로 재시도` : `${TITLES[section]} 조회 실패 · 새로고침으로 재시도`;
          status.dataset.failed = "true";
          if (!previous) {
            const placeholders: Record<SectionName, string> = {
              performance: "#perf-saving-note,#perf-comparison,#perf-chart-note,#perf-contribution,#perf-trend-table,#perf-observation",
              daily: "#perf-today-basis,#perf-attention-summary,#adm-daily-compact", coverage: "#adm-heatmap",
            };
            this.root.querySelectorAll(`${placeholders[section]},[data-placeholder="${section}"]`).forEach(el => {
              el.textContent = `${TITLES[section]}를 불러오지 못했습니다. 새로고침으로 다시 시도해 주세요.`;
            });
          }
        }
      } finally {
        clearTimeout(timeout);
        this.aborters.delete(aborter);
        region?.setAttribute("aria-busy", "false");
      }
    }));
    this.inFlight = false;
    if (this.refreshButton) this.refreshButton.disabled = false;
  }

  destroy(): void {
    this.disposed = true;
    clearInterval(this.timer);
    this.aborters.forEach(a => a.abort());
    document.removeEventListener("visibilitychange", this.visibility);
    this.refreshButton?.removeEventListener("click", this.manual);
  }
}
