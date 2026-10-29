export interface ModuleSetting {
  module_id: string;
  name: string;
  estimated_manual_seconds: number;
  manifest_default: number;
  is_overridden: boolean;
}
export interface SystemSettings { system_code: string; system_name: string; modules: ModuleSetting[] }
export interface EditableModule extends ModuleSetting { draft: string }
export interface EditableSystem extends Omit<SystemSettings, "modules"> { modules: EditableModule[] }
export interface SavedModule { module_id: string; estimated_manual_seconds: number }
export interface BulkResult { ok: boolean; saved: SavedModule[]; failed?: { module_id: string; detail: string }[] }
export interface ModulesState {
  systems: EditableSystem[];
  selected: string | null;
  systemQuery: string;
  moduleQuery: string;
  filter: "all" | "custom" | "dirty";
  page: number;
  pageSize: number;
  busy: boolean;
  loading: boolean;
  loadError: string;
  feedback: string;
  feedbackError: boolean;
}
