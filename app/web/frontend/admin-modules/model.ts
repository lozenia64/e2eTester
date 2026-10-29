import type { EditableModule, ModulesState } from "./types";

export const currentSystem = (s: ModulesState) => s.systems.find(system => system.system_code === s.selected);
export const validTime = (m: EditableModule) => m.draft.trim() !== "" && Number.isSafeInteger(Number(m.draft)) && Number(m.draft) >= 0;
export const isDirty = (m: EditableModule) => !validTime(m) || Number(m.draft) !== m.estimated_manual_seconds;
export const changedModules = (s: ModulesState) => currentSystem(s)?.modules.filter(isDirty) ?? [];
export function visibleModules(s: ModulesState) {
  const query = s.moduleQuery.trim().toLocaleLowerCase();
  return currentSystem(s)?.modules.filter(m => `${m.name} ${m.module_id}`.toLocaleLowerCase().includes(query) && (s.filter === "all" || s.filter === "custom" && m.is_overridden || s.filter === "dirty" && isDirty(m))) ?? [];
}
export function duration(seconds: number) {
  if (!Number.isSafeInteger(seconds) || seconds < 0) return "값 확인 필요";
  const min = Math.floor(seconds / 60), sec = seconds % 60;
  return min ? `${min.toLocaleString()}분${sec ? ` ${sec}초` : ""}` : `${sec}초`;
}
export function resetDraft(s: ModulesState) {
  currentSystem(s)?.modules.forEach(m => { m.draft = String(m.estimated_manual_seconds); });
  s.feedback = ""; s.feedbackError = false;
}
export function initialState(): ModulesState {
  return { systems: [], selected: null, systemQuery: "", moduleQuery: "", filter: "all", page: 1, pageSize: 10, busy: false, loading: true, loadError: "", feedback: "", feedbackError: false };
}
