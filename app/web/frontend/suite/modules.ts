// 모듈 칩 · 수트 모듈 집계 · "지금 실행 중" 카드 모델. DOM 을 모르는 순수 계산(설계 §2·§3).
// 칩(steps.ts)과 요약(render.ts)이 같은 데이터에서 같은 함수로 계산해야 숫자가 칩과 어긋나지 않는다.
import { normalizeTone, statusLabel } from "../components/status-badge/index";
import type { StatusTone } from "../lib/status.generated";
import { computeRunModuleProgress, orderedSelectedRunModules } from "./progress";
import type { SuiteLike, SuiteStepLike } from "./render";

const SUITE_ACTIVE_STATUSES = new Set(["pending", "running", "waiting_input"]);

export type ModuleChip = { moduleId: string; name: string; tone: StatusTone };

type RunModuleLike = { module_id?: string; name?: string; status?: unknown; started_at?: string | null };

export function buildModuleChips(run: unknown): ModuleChip[] {
  return (orderedSelectedRunModules(run) as RunModuleLike[]).map((module) => ({
    moduleId: String(module.module_id ?? ""),
    name: module.name ?? "",
    tone: normalizeTone(String(module.status ?? "")),
  }));
}

export type SuiteModuleSummary = {
  done: number;
  total: number;
  percent: number;
  passed: number;
  failed: number;
  blocked: number;
  remaining: number;
};

export function summarizeSuiteModules(
  steps: SuiteStepLike[],
  runs: ReadonlyMap<string, unknown>,
): SuiteModuleSummary {
  let total = 0;
  let passed = 0;
  let failed = 0;
  let blocked = 0;
  let cancelled = 0;
  for (const step of steps) {
    const status = String(step.status ?? "").toLowerCase();
    if (status === "skipped") {
      continue;
    }
    const run = step.run_id ? runs.get(step.run_id) : undefined;
    if (run === undefined) {
      // 페이로드 도착 전 — passed 스텝은 전부 통과로 둬서 0% 로 깜빡이지 않게 한다.
      const count = step.module_total ?? 0;
      total += count;
      if (status === "passed") {
        passed += count;
      }
      continue;
    }
    for (const chip of buildModuleChips(run)) {
      total += 1;
      if (chip.tone === "passed") passed += 1;
      else if (chip.tone === "error" || chip.tone === "anomaly") failed += 1;
      else if (chip.tone === "blocked") blocked += 1;
      else if (chip.tone === "cancelled") cancelled += 1;
    }
  }
  const done = passed + failed + blocked + cancelled;
  return {
    done,
    total,
    percent: total ? Math.round((done / total) * 100) : 0,
    passed,
    failed,
    blocked,
    remaining: total - done,
  };
}

// socket.ts 에서 옮겼다 — describeNow 가 소켓과 같은 규칙으로 활성 run 을 찾는다.
export function resolveActiveSuiteRunId(suite: SuiteLike | null | undefined): string | null {
  if (suite?.awaiting_input_run_id) {
    return suite.awaiting_input_run_id;
  }
  if (suite?.active_run_id) {
    return suite.active_run_id;
  }
  const activeStep = (suite?.steps ?? []).find((step) => {
    const status = String(step.status).toLowerCase();
    return step.run_id && (status === "running" || status === "waiting_input");
  });
  return activeStep?.run_id ?? null;
}

export type NowCard =
  | {
      kind: "running" | "waiting";
      systemName: string;
      moduleName: string;
      moduleStartedAt: string | null;
      systemIndex: number;
      systemTotal: number;
      moduleIndex: number;
      moduleTotal: number;
    }
  | { kind: "idle" }
  | { kind: "finished"; statusLabel: string; passed: number; failed: number };

export function describeNow(
  suite: SuiteLike,
  runs: ReadonlyMap<string, unknown>,
  summary: SuiteModuleSummary,
): NowCard {
  const suiteStatus = String(suite.status ?? "").toLowerCase();
  if (!SUITE_ACTIVE_STATUSES.has(suiteStatus)) {
    return { kind: "finished", statusLabel: statusLabel(suiteStatus), passed: summary.passed, failed: summary.failed };
  }
  const runId = resolveActiveSuiteRunId(suite);
  const selected = (suite.steps ?? []).filter((step) => String(step.status ?? "").toLowerCase() !== "skipped");
  const stepIndex = runId ? selected.findIndex((step) => step.run_id === runId) : -1;
  const step = selected[stepIndex];
  if (!step) {
    return { kind: "idle" };
  }
  const run = runs.get(runId!);
  const progress = computeRunModuleProgress(run);
  const modules = orderedSelectedRunModules(run) as RunModuleLike[];
  const module = progress.current > 0 ? modules[progress.current - 1] : undefined;
  const waiting = suiteStatus === "waiting_input" || progress.tone === "waiting";
  return {
    kind: waiting ? "waiting" : "running",
    systemName: step.system_name ?? "",
    moduleName: progress.moduleName,
    moduleStartedAt: progress.moduleName ? (module?.started_at ?? null) : null,
    systemIndex: stepIndex + 1,
    systemTotal: selected.length,
    moduleIndex: run === undefined ? 0 : progress.current,
    moduleTotal: run === undefined ? (step.module_total ?? 0) : progress.total,
  };
}
