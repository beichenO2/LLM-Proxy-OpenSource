export interface IProjectOut {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface IProjectListResponse {
  items: IProjectOut[];
  total: number;
}

export interface IVaultStatus {
  locked: boolean;
  has_session: boolean;
  role: "admin" | "user" | "readonly" | "service" | null;
}

export interface IUserOut {
  id: string;
  username: string;
  role: string;
  created_at: string;
  updated_at: string;
}

export interface IUserListResponse {
  items: IUserOut[];
  total: number;
}

export interface IIdentityOut {
  id: string;
  key: string;
  value: string;
  project_id: string | null;
  category: string | null;
  created_at: string;
  updated_at: string;
}

export interface IIdentityListResponse {
  items: IIdentityOut[];
  total: number;
}

export interface ISecretOut {
  id: string;
  key: string;
  enabled: boolean;
  project_id: string | null;
  base_url: string | null;
  category: string | null;
  rotated_at: string | null;
  created_at: string;
  updated_at: string;
  has_value: boolean;
}

export interface ISecretListResponse {
  items: ISecretOut[];
  total: number;
}

export interface IBindingOut {
  id: string;
  service_name: string;
  secret_ref_key: string;
  auth_header: string | null;
  project_id: string | null;
  resolved: boolean;
  fallback_chain: string[] | null;
  priority: number;
  cooldown_until: string | null;
  consecutive_failures: number;
  created_at: string;
  updated_at: string;
}

export interface IBindingListResponse {
  items: IBindingOut[];
  total: number;
}

export interface IFallbackConfig {
  fallback_chain: string[] | null;
  priority: number | null;
}

export interface IBindingStatus {
  id: string;
  service_name: string;
  is_cooling_down: boolean;
  cooldown_until: string | null;
  consecutive_failures: number;
  fallback_chain: string[] | null;
}

export interface IAuditItem {
  id: string;
  action: string;
  detail: string | null;
  project_id: string | null;
  created_at: string;
}

export interface IAuditListResponse {
  items: IAuditItem[];
}

export interface IDashboardSummary {
  identity_count: number;
  secret_count: number;
  binding_count: number;
  project_id: string | null;
}

export interface IRecentProjectOut {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface IRecentProjectsResponse {
  items: IRecentProjectOut[];
}

export interface IRecentEntryOut {
  id: string;
  type: "identity" | "secret";
  key: string;
  value: string | null;
  has_value: boolean;
  project_id: string | null;
  category: string | null;
  created_at: string;
}

export interface IRecentEntriesResponse {
  items: IRecentEntryOut[];
  total: number;
}

export interface IConnectivityResult {
  reachable: boolean;
  status_code: number | null;
  latency_ms: number;
  error: string | null;
}

export interface IOnboardingStatus {
  completed: boolean;
  has_db: boolean;
  has_vault: boolean;
}

export interface ISettingsGetResponse {
  api_port: number | null;
  preferences: Record<string, unknown>;
}

export interface ILogItem {
  timestamp: string;
  level: string;
  source: string;
  message: string;
}

export interface ILogListResponse {
  items: ILogItem[];
}

export interface ITestResultRow {
  name: string;
  status: "pass" | "fail" | "skip";
  message: string;
  duration_ms: number;
}

export interface IRunResponse {
  results: ITestResultRow[];
}

export interface IRenderResponse {
  rendered: string;
  warnings: Array<Record<string, unknown>>;
}

export interface ILLMServiceStatus {
  service_name: string;
  last_call_at: string | null;
  last_call_status: string | null;
  last_call_error: string | null;
  last_call_latency_ms: number | null;
  last_success_at: string | null;
  consecutive_failures: number;
}

export interface ILLMStatusResponse {
  services: ILLMServiceStatus[];
}
