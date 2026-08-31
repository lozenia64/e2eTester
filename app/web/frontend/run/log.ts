// 실행 로그 저장소 — 필터·상한·내보내기. DOM 을 모른다(설계 §3.3).
//
// 상한은 표시에만 건다. 복사·다운로드는 전량을 대상으로 한다 — 조사 도구의
// 본질이라 잘라내면 안 된다.

export type LogEntry = { moduleId: string; message: string };

const DISPLAY_CAP = 2000;

let entries: LogEntry[] = [];
let moduleFilterId = "";
let searchTerm = "";
let filterManual = false;

function matchesFilters(entry: LogEntry): boolean {
  if (moduleFilterId && entry.moduleId !== moduleFilterId) return false;
  return !searchTerm || entry.message.toLowerCase().includes(searchTerm);
}

function filteredEntries(): LogEntry[] {
  return entries.filter(matchesFilters);
}

function formatLine(entry: LogEntry): string {
  return entry.moduleId ? `[${entry.moduleId}] ${entry.message}` : entry.message;
}

export function resetLog(nextEntries: LogEntry[]): void {
  entries = [...nextEntries];
}

export function pushLog(entry: LogEntry): void {
  entries.push(entry);
}

export function setModuleFilter(moduleId: string, opts?: { manual?: boolean }): void {
  if (opts?.manual === undefined && filterManual) return;
  moduleFilterId = moduleId;
  filterManual = opts?.manual === true;
}

export function setSearch(term: string): void {
  searchTerm = term.trim().toLowerCase();
}

export function isFilterManual(): boolean {
  return filterManual;
}

export function visibleEntries(): LogEntry[] {
  return filteredEntries().slice(-DISPLAY_CAP);
}

export function hiddenCount(): number {
  return Math.max(0, filteredEntries().length - DISPLAY_CAP);
}

export function exportText(): string {
  return filteredEntries().map(formatLine).join("\n");
}
