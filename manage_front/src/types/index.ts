export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
  username: string;
  role: string;
}

export type BusinessRole = "unassigned" | "employee" | "general_manager";
export type DepartmentCode = "product" | "hr" | "engineering" | "finance";

export interface BusinessAssignment {
  business_role: BusinessRole;
  department_code: DepartmentCode | null;
  portal_user_id: number | null;
}

export interface UserUpdate extends Partial<BusinessAssignment> {
  role?: string;
  quota_tier?: string;
  runtime_mode?: string;
  is_active?: boolean;
}

export interface UserCreate extends UserUpdate {
  username: string;
  email: string;
  password: string;
}

export interface UserCreateResult extends BusinessAssignment {
  id: string;
  username: string;
  capabilities: string[];
}

export interface UserSummary extends BusinessAssignment {
  id: string;
  username: string;
  email: string;
  role: string;
  quota_tier: string;
  runtime_mode: string;
  is_active: boolean;
  created_at: string;
  container_status: string | null;
  container_docker_id: string | null;
  container_created_at: string | null;
  shared_agent_id: string | null;
  shared_agent_status: string | null;
  tokens_used_today: number;
  tokens_used_7d: number;
  tokens_used_total: number;
  capabilities: string[];
}

export interface PaginatedUsers {
  items: UserSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface UsageSummary {
  total_tokens_today: number;
  total_users: number;
  active_containers: number;
}

export interface DailyUsage {
  date: string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
}

export interface ModelUsage {
  model: string;
  total_tokens: number;
}

export interface UsageHistory {
  daily: DailyUsage[];
  by_model: ModelUsage[];
}

export interface AuditLogItem {
  id: string;
  user_id: string | null;
  username: string | null;
  action: string;
  resource: string | null;
  detail: string | null;
  created_at: string;
}

export interface PaginatedAuditLogs {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
}
