export interface AdminUser {
  user_id: string;
  name: string;
  email: string;
  role: "admin" | "user";
  is_active: boolean;
  created_at: string;
  allowed_system_codes: string[];
}

export interface AccessSystem { system_code: string; system_name: string }
export type UserFilter = "all" | "active" | "inactive";

export interface UsersState {
  users: AdminUser[];
  systems: AccessSystem[];
  selectedId: string | null;
  filter: UserFilter;
  query: string;
  draft: string[];
  all: boolean;
  loading: boolean;
  busy: boolean;
  systemsReady: boolean;
  error: string;
  detailError: string;
}
