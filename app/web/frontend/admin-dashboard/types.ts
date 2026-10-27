export interface PerformanceData {
  generated_at: string;
  timezone: string;
  period: { from: string; to: string; previous_from: string; previous_to: string };
  total_seconds: number;
  previous_seconds: number;
  change_percent: number | null;
  total_runs: number;
  basis_note: string;
  by_system: { system_code: string; system_name: string; saved_seconds: number; runs: number }[];
  daily: { date: string; saved_seconds: number; cumulative_seconds: number }[];
}
export interface DailyModule {
  module_id: string; name: string; status_label: string; tone: string; run_id: string | null;
}
export interface DailyData {
  generated_at: string; date_label: string;
  totals: { systems: number; modules: number; passed: number; inspected: number; pass_rate: number; anomaly: number; error: number };
  systems: { system_code: string; system_name: string; module_total: number; inspected: number;
    pass_rate: number; latest_run_id: string | null; latest_run_tone: string;
    latest_run_status_label: string; modules: DailyModule[]; counts: Record<string, number> }[];
}
export interface CoverageData {
  generated_at: string;
  columns: { day_key: string; slot_id: string; label: string }[];
  systems: { system_code: string; system_name: string; latest_tone: string;
    cells: { day_key: string; slot_id: string; status_label: string; tone: string; run_id: string | null; checked_at: string | null }[] }[];
}
export type SectionName = "performance" | "daily" | "coverage";
