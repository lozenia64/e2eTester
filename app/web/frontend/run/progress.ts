export type ModuleProgress = { status: string };

export type ModuleSummary = {
  passed: number;
  failed: number;
  total: number;
  percent: number;
};

export function formatClock(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export function summarizeModules(modules: ModuleProgress[]): ModuleSummary {
  const statuses = modules.map(({ status }) => status.toLowerCase());
  const total = statuses.filter((status) => status !== "skipped").length;
  const passed = statuses.filter((status) => status === "passed").length;
  const failed = statuses.filter((status) =>
    ["anomaly", "error", "failed", "blocked"].includes(status),
  ).length;
  const percent = total === 0 ? 0 : Math.round(((passed + failed) / total) * 100);
  return { passed, failed, total, percent };
}
