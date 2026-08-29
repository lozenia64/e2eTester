// app/web/static/app.js 의 orderedSelectedRunModules · computeRunModuleProgress 를
// 로직 변경 없이 이관하고 타입만 얹었다(설계 §3.5). DOM 을 모르는 순수 계산.
// moduleProgressClassName 은 이관하지 않는다 — Task 6 이 data-tone 속성으로 대체한다.
import { normalizeTone } from "../components/status-badge/index";

const SUITE_ACTIVE_MODULE_STATUSES = new Set(["running", "waiting_input"]);
const ACTIVE_RUN_STATUSES = new Set(["pending", "running", "waiting_input"]);

// app.js 원본은 window.__statusBadge.normalizeTone 을 썼다 — jsdom 에 그 전역이 없으므로
// 컴포넌트 모듈에서 직접 import 한다. normalizeTone 이 내부에서 String(x ?? "") 코어션을
// 하므로 동작은 동일하다.
const normalizeOutcomeStatus = (status: unknown): string => normalizeTone(String(status ?? ""));

const isModuleIssueStatus = (status: unknown): boolean => {
  const normalized = normalizeOutcomeStatus(status);
  return normalized === "anomaly" || normalized === "error";
};

export type ModuleProgress = {
  current: number;
  total: number;
  label: string;
  moduleName: string;
  tone: string;
};

type RunModuleLike = {
  module_id?: string;
  name?: string;
  order: number;
  status?: unknown;
};

type RunLike = {
  status?: unknown;
  modules?: RunModuleLike[];
  selected_module_ids?: unknown[];
};

export function orderedSelectedRunModules(run: unknown): unknown[] {
  const data = run as RunLike | null | undefined;
  const modules = [...(data?.modules ?? [])].sort((left, right) => left.order - right.order);
  const selectedIds = new Set(
    data?.selected_module_ids?.length
      ? data.selected_module_ids
      : modules
          .filter((module) => String(module.status).toLowerCase() !== "skipped")
          .map((module) => module.module_id),
  );
  return modules.filter((module) => selectedIds.has(module.module_id));
}

export function computeRunModuleProgress(run: unknown): ModuleProgress {
  const data = run as RunLike | null | undefined;
  const modules = orderedSelectedRunModules(run) as RunModuleLike[];
  const total = modules.length || data?.selected_module_ids?.length || 0;
  if (total === 0) {
    return { current: 0, total: 0, label: "", moduleName: "", tone: "muted" };
  }

  const activeIndex = modules.findIndex((module) =>
    SUITE_ACTIVE_MODULE_STATUSES.has(String(module.status).toLowerCase()),
  );
  if (activeIndex >= 0) {
    const module = modules[activeIndex]!;
    return {
      current: activeIndex + 1,
      total,
      label: `${activeIndex + 1}/${total}`,
      moduleName: module.name ?? "",
      tone: String(module.status).toLowerCase() === "waiting_input" ? "waiting" : "active",
    };
  }

  const passedCount = modules.filter((module) => String(module.status).toLowerCase() === "passed").length;
  const issueIndex = modules.findIndex((module) => isModuleIssueStatus(module.status));
  const runStatus = normalizeOutcomeStatus(data?.status);

  if (issueIndex >= 0 && (runStatus === "anomaly" || runStatus === "error")) {
    return {
      current: issueIndex + 1,
      total,
      label: `${issueIndex + 1}/${total}`,
      moduleName: modules[issueIndex]!.name ?? "",
      tone: runStatus === "error" ? "error" : "anomaly",
    };
  }

  if (ACTIVE_RUN_STATUSES.has(runStatus) && passedCount < total) {
    return {
      current: passedCount + 1,
      total,
      label: `${passedCount + 1}/${total}`,
      moduleName: "",
      tone: "active",
    };
  }

  if (runStatus === "passed") {
    return {
      current: total,
      total,
      label: `${total}/${total}`,
      moduleName: "",
      tone: "passed",
    };
  }

  return {
    current: passedCount,
    total,
    label: passedCount > 0 ? `${passedCount}/${total}` : "",
    moduleName: "",
    tone: "muted",
  };
}
