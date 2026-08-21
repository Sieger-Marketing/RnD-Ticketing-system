/**
 * Types mirroring the backend's Pydantic schemas.
 *
 * Kept hand-written rather than generated so the shapes stay readable, but
 * they are a contract: if a field here disagrees with the API, the screen
 * using it is wrong, not the type.
 */

export type UUID = string;
export type ISODate = string;
export type ISODateTime = string;

/** Every list endpoint returns this envelope. */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/** Every failure returns this envelope, whatever the status code. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

// ---------------------------------------------------------------------------
// Vocabularies
// ---------------------------------------------------------------------------

export type Health = "GREEN" | "AMBER" | "RED";
export type Priority = "Low" | "Medium" | "High" | "Critical";

export type TaskStatus =
  | "Not Started"
  | "Assigned"
  | "In Progress"
  | "Blocked"
  | "Submitted for Review"
  | "Under Review"
  | "Revision Required"
  | "Approved"
  | "Completed"
  | "Cancelled";

export type ReleaseStatus =
  | "Draft"
  | "Assigned"
  | "Planning"
  | "In Progress"
  | "Internal Review"
  | "Revision"
  | "Approved"
  | "Completed"
  | "On Hold"
  | "Cancelled";

export type ProjectStatus =
  | "Not Started"
  | "Planning"
  | "Design In Progress"
  | "Internal Review"
  | "Customer Review"
  | "Revision"
  | "Approved"
  | "Completed"
  | "On Hold"
  | "Cancelled";

export type RoleName = "Director" | "Design Manager" | "Team Lead" | "Designer";

export type UtilizationBand =
  | "Underutilized"
  | "Healthy"
  | "High Load"
  | "Overloaded"
  | "No Data";

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface CurrentUser {
  id: UUID;
  code: string;
  email: string;
  full_name: string;
  designation: string | null;
  department: string | null;
  roles: string[];
  primary_role: string | null;
  permissions: string[];
  home_route: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: CurrentUser;
}

// ---------------------------------------------------------------------------
// People
// ---------------------------------------------------------------------------

export interface UserSkill {
  skill_id: UUID;
  name: string | null;
  category: string | null;
  level: string;
  level_rank: number;
  years_experience: number | null;
}

export interface User {
  id: UUID;
  code: string;
  email: string;
  /** What people sign in with, e.g. SIES00267. Absent for the administrator. */
  employee_code: string | null;
  full_name: string;
  designation: string | null;
  department: string | null;
  phone: string | null;
  is_active: boolean;
  reports_to_id: UUID | null;
  standard_daily_hours: number;
  working_days_per_week: number;
  last_login_at: ISODateTime | null;
  created_at: ISODateTime;
  roles: string[];
  skills: UserSkill[];
}

export interface Skill {
  id: UUID;
  name: string;
  category: string | null;
  description: string | null;
  is_active: boolean;
}

export interface CapacityDay {
  date: string;
  available: number;
  allocated: number;
  utilization_percent: number | null;
}

export interface CapacitySummary {
  user_id: string;
  code: string | null;
  full_name: string;
  designation: string | null;
  period_start: string;
  period_end: string;
  available_hours: number;
  allocated_hours: number;
  logged_hours: number;
  utilization_percent: number | null;
  utilization_band: UtilizationBand;
  open_tasks: number;
  next_deadline: string | null;
  skills: { skill_id: string; name: string | null; level: string; level_rank: number }[];
  daily: CapacityDay[];
  has_required_skill?: boolean | null;
  skill_rank?: number | null;
  headroom_hours?: number | null;
}

// ---------------------------------------------------------------------------
// Catalog
// ---------------------------------------------------------------------------

export interface Customer {
  id: UUID;
  code: string;
  name: string;
  customer_code: string;
  industry: string | null;
  country: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  is_active: boolean;
}

export interface Product {
  id: UUID;
  code: string;
  name: string;
  product_family_id: UUID | null;
  product_family_name: string | null;
  description: string | null;
  is_active: boolean;
}

export interface ProductFamily {
  id: UUID;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
}

// ---------------------------------------------------------------------------
// Health findings
// ---------------------------------------------------------------------------

/** Why an entity is amber or red. The engine never returns a bare colour. */
export interface HealthReason {
  level: Health;
  code: string;
  message: string;
  value: number | string | null;
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export interface ProjectSummary {
  id: UUID;
  code: string;
  name: string;
  customer_id: UUID | null;
  customer_name: string | null;
  product_id: UUID | null;
  product_name: string | null;
  project_type: string | null;
  priority: Priority;
  status: ProjectStatus;
  health: Health;
  completion_percent: number;
  planned_hours: number;
  actual_hours: number;
  rework_hours: number;
  delay_days: number;
  revision_count: number;
  start_date: ISODate | null;
  required_completion_date: ISODate | null;
  design_manager_name: string | null;
  release_count: number;
  task_count: number;
  /** Car spaces the system provides. */
  car_count: number | null;
  /** Good-for-construction date. */
  gfc_date: ISODate | null;
}

export interface ProjectDetail extends ProjectSummary {
  description: string | null;
  sales_order: string | null;
  work_order: string | null;
  internal_deadline: ISODate | null;
  customer_deadline: ISODate | null;
  actual_completion_date: ISODate | null;
  health_reasons: HealthReason[];
  external_id: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  efficiency_percent: number | null;
  effort_variance: number | null;
}

// ---------------------------------------------------------------------------
// Releases
// ---------------------------------------------------------------------------

export interface ReleaseSummary {
  id: UUID;
  code: string;
  project_id: UUID;
  project_code: string | null;
  project_name: string | null;
  sequence_number: number;
  name: string;
  release_type: string;
  priority: Priority;
  status: ReleaseStatus;
  review_status: string;
  health: Health;
  completion_percent: number;
  estimated_hours: number;
  actual_hours: number;
  rework_hours: number;
  revision_count: number;
  delay_days: number;
  planned_start: ISODate | null;
  planned_end: ISODate | null;
  team_lead_id: UUID | null;
  team_lead_name: string | null;
  task_count: number;
  /** How many of this system the project takes. */
  unit_count: number | null;
}

export interface ReleaseDetail extends ReleaseSummary {
  description: string | null;
  actual_start: ISODate | null;
  actual_end: ISODate | null;
  health_reasons: HealthReason[];
  template_version_id: UUID | null;
  template_name: string | null;
  template_version_label: string | null;
  delay_reason: string | null;
  delay_note: string | null;
  completion_override_reason: string | null;
  efficiency_percent: number | null;
  effort_variance: number | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

export interface TemplateTask {
  id: UUID;
  sequence: number;
  name: string;
  task_type: string;
  description: string | null;
  default_estimated_hours: number;
  default_priority: Priority;
  complexity: number;
  required_skill_id: UUID | null;
  is_mandatory: boolean;
  requires_review: boolean;
  depends_on_sequence: number | null;
  /** False means the prerequisite is the expected order, not a gate. */
  depends_on_blocking: boolean;
}

export interface TemplateVersion {
  id: UUID;
  version_number: number;
  label: string;
  is_published: boolean;
  published_at: ISODateTime | null;
  change_note: string | null;
  task_count: number;
  total_estimated_hours: number;
  tasks: TemplateTask[];
}

export interface DesignTemplate {
  id: UUID;
  code: string;
  name: string;
  description: string | null;
  release_type: string;
  product_id: UUID | null;
  product_name: string | null;
  product_family_id: UUID | null;
  product_family_name: string | null;
  is_active: boolean;
  current_version_number: number | null;
  versions: TemplateVersion[];
}

export interface TemplateSuggestion {
  suggested: {
    template_id: UUID;
    template_name: string;
    version_id: UUID;
    version_number: number;
    task_count: number;
    total_estimated_hours: number;
  } | null;
  alternatives: {
    template_id: UUID;
    template_name: string;
    version_id: UUID | null;
    version_number: number | null;
  }[];
}

// ---------------------------------------------------------------------------
// Tasks
// ---------------------------------------------------------------------------

export interface TaskDependency {
  id: UUID;
  depends_on_task_id: UUID;
  depends_on_code: string | null;
  depends_on_name: string | null;
  depends_on_status: TaskStatus | null;
  dependency_type: string;
  is_blocking: boolean;
  is_satisfied: boolean;
}

export interface TaskSummary {
  id: UUID;
  code: string;
  project_id: UUID;
  project_code: string | null;
  release_id: UUID;
  release_code: string | null;
  name: string;
  task_type: string;
  status: TaskStatus;
  review_status: string;
  priority: Priority;
  complexity: number;
  is_mandatory: boolean;
  requires_review: boolean;
  completion_percent: number;
  estimated_hours: number;
  actual_hours: number;
  rework_hours: number;
  revision_count: number;
  delay_days: number;
  is_overdue: boolean;
  planned_start: ISODate | null;
  planned_end: ISODate | null;
  assigned_to_id: UUID | null;
  assigned_to_name: string | null;
  required_skill_name: string | null;
  blocker_reason: string | null;
}

export interface TaskDetail extends TaskSummary {
  description: string | null;
  sequence: number;
  team_lead_id: UUID | null;
  original_estimated_hours: number;
  blocked_hours: number;
  submission_count: number;
  delay_reason: string | null;
  delay_note: string | null;
  assigned_at: ISODateTime | null;
  started_at: ISODateTime | null;
  submitted_at: ISODateTime | null;
  completed_at: ISODateTime | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  efficiency_percent: number | null;
  effort_variance: number | null;
  cycle_time_hours: number | null;
  queue_time_hours: number | null;
  dependencies: TaskDependency[];
  blocked_by: TaskDependency[];
  can_start: boolean;
  allowed_transitions: TaskStatus[];
}

export interface KanbanColumn {
  key: string;
  title: string;
  statuses: TaskStatus[];
  count: number;
  tasks: TaskSummary[];
}

export interface KanbanBoard {
  columns: KanbanColumn[];
  total: number;
}

// ---------------------------------------------------------------------------
// Execution
// ---------------------------------------------------------------------------

export interface TimeEntry {
  id: UUID;
  code: string;
  task_id: UUID;
  task_code: string | null;
  task_name: string | null;
  user_id: UUID;
  user_name: string | null;
  entry_date: ISODate;
  started_at: ISODateTime | null;
  ended_at: ISODateTime | null;
  hours: number;
  source: string;
  is_running: boolean;
  is_rework: boolean;
  revision_id: UUID | null;
  description: string | null;
}

export interface Review {
  id: UUID;
  code: string;
  task_id: UUID;
  task_code: string | null;
  task_name: string | null;
  round_number: number;
  status: string;
  result: string | null;
  reviewer_id: UUID | null;
  reviewer_name: string | null;
  submitted_at: ISODateTime;
  review_started_at: ISODateTime | null;
  reviewed_at: ISODateTime | null;
  turnaround_hours: number | null;
  comments: string | null;
}

export interface Revision {
  id: UUID;
  code: string;
  task_id: UUID;
  task_code: string | null;
  task_name: string | null;
  revision_number: number;
  reason: string;
  category: string;
  accountability: "Controllable" | "External";
  root_cause: string | null;
  assigned_to_id: UUID | null;
  assigned_to_name: string | null;
  raised_date: ISODateTime;
  resolved_date: ISODateTime | null;
  additional_hours: number;
  status: string;
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export interface DepartmentMetrics {
  period: { from: string; to: string };
  active_projects: number;
  completed_projects: number;
  active_releases: number;
  overdue_releases: number;
  active_tasks: number;
  completed_tasks: number;
  overdue_tasks: number;
  blocked_tasks: number;
  pending_reviews: number;
  open_revisions: number;
  planned_hours: number;
  actual_hours: number;
  rework_hours: number;
  efficiency_percent: number | null;
  utilization_percent: number | null;
  available_hours: number;
  allocated_hours: number;
  on_time_percent: number | null;
  rework_percent: number | null;
  first_pass_approval_percent: number | null;
  revision_rate_percent: number | null;
  average_cycle_time_hours: number | null;
  average_review_turnaround_hours: number | null;
  health_breakdown: Record<Health, number>;
}

export interface PerformanceScore {
  score: number | null;
  components: Record<string, number | null>;
  weights_applied: Record<string, number>;
}

export interface DesignerMetrics {
  user: { id: string; code: string; full_name: string; designation: string | null };
  period: { from: string; to: string };
  tasks_assigned: number;
  tasks_completed: number;
  tasks_pending: number;
  tasks_overdue: number;
  planned_hours: number;
  actual_hours: number;
  logged_hours: number;
  rework_hours: number;
  blocked_hours: number;
  efficiency_percent: number | null;
  effort_variance: number;
  utilization_percent: number | null;
  utilization_band: UtilizationBand;
  available_hours: number;
  allocated_hours: number;
  on_time_percent: number | null;
  rework_percent: number | null;
  revision_count: number;
  controllable_revision_count: number;
  first_pass_approval_percent: number | null;
  average_cycle_time_hours: number | null;
  average_queue_time_hours: number | null;
  effort_weighted_output: number;
  performance_score: PerformanceScore;
}

export interface MonthlyTrend {
  month: string;
  tasks_completed: number;
  releases_completed: number;
  planned_hours: number;
  actual_hours: number;
  rework_hours: number;
  efficiency_percent: number | null;
  on_time_percent: number | null;
  rework_percent: number | null;
}

export interface Insight {
  severity: "critical" | "warning" | "positive";
  code: string;
  message: string;
  entity_type: string;
  entity_id: string;
  value: number | string | null;
}

export interface Notification {
  id: UUID;
  event_type: string;
  title: string;
  body: string | null;
  severity: "Info" | "Warning" | "Critical";
  entity_type: string | null;
  entity_id: UUID | null;
  is_read: boolean;
  read_at: ISODateTime | null;
  created_at: ISODateTime;
}

/** One standard design release a product produces. */
export interface ReleaseStandard {
  id: UUID;
  sequence: number;
  name: string;
  is_default: boolean;
  condition: string | null;
  alternative_name: string | null;
}

/** A named set of releases -- "standard", or a size-driven alternative. */
export interface StandardVariant {
  variant: string;
  condition: string | null;
  releases: ReleaseStandard[];
}

export interface ProductStandard {
  product_id: UUID;
  product_name: string;
  tasks: string[];
  variants: StandardVariant[];
}

export interface Role {
  id: UUID;
  name: string;
  description: string | null;
  permissions: string[];
}

/** Returned once when an administrator resets someone's password. */
export interface PasswordReset {
  user_id: UUID;
  employee_code: string | null;
  full_name: string;
  password: string;
}

/** One row of a performance breakdown, whatever it is cut by. */
export interface BreakdownRow {
  key: UUID | null;
  label: string;
  projects: number;
  releases: number;
  tasks_completed: number;
  tasks_open: number;
  tasks_overdue: number;
  planned_hours: number;
  actual_hours: number;
  rework_hours: number;
  efficiency_percent: number | null;
  effort_variance_hours: number;
  on_time_percent: number | null;
  rework_percent: number | null;
  first_pass_approval_percent: number | null;
  revision_rate_percent: number | null;
  average_cycle_time_hours: number | null;
  health: { RED: number; AMBER: number; GREEN: number };
}

export interface BreakdownTotals {
  tasks_completed: number;
  tasks_open: number;
  tasks_overdue: number;
  planned_hours: number;
  actual_hours: number;
  rework_hours: number;
  efficiency_percent: number | null;
  effort_variance_hours: number;
  on_time_percent: number | null;
  rework_percent: number | null;
  first_pass_approval_percent: number | null;
  revision_rate_percent: number | null;
  average_cycle_time_hours: number | null;
}

export interface Breakdown {
  dimension: string;
  row_label: string;
  period: { from: string; to: string };
  within: { dimension: string; key: string } | null;
  rows: BreakdownRow[];
  totals: BreakdownTotals;
}

export interface ReportDefinition {
  key: string;
  title: string;
  description: string;
  parameter: string;
  parameter_label: string;
  parameter_options?: string[];
  accepts_period?: boolean;
}

export interface ReportCatalogue {
  formats: string[];
  reports: ReportDefinition[];
}

export interface AppSetting {
  id: UUID;
  key: string;
  category: string;
  value: unknown;
  description: string | null;
  is_system: boolean;
  updated_at: ISODateTime;
}
