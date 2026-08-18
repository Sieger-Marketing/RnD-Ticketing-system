/**
 * Data-fetching hooks.
 *
 * One hook per endpoint, with query keys structured so an invalidation after a
 * mutation refreshes exactly the affected screens. Nothing here computes a
 * metric -- every number arrives already calculated by the backend, which is
 * what keeps the KPI definitions in one place.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { del, get, patch, post, put } from "@/lib/api";
import type {
  CapacitySummary,
  Customer,
  DepartmentMetrics,
  DesignTemplate,
  DesignerMetrics,
  Insight,
  KanbanBoard,
  MonthlyTrend,
  Notification,
  Page,
  Product,
  ProductFamily,
  ProjectDetail,
  ProjectSummary,
  ReleaseDetail,
  ReleaseSummary,
  Review,
  Revision,
  Skill,
  TaskDetail,
  TaskSummary,
  TemplateSuggestion,
  TimeEntry,
  User,
  UUID,
} from "@/types/api";

type Params = Record<string, unknown>;

export const keys = {
  projects: (p?: Params) => ["projects", p ?? {}] as const,
  project: (id: UUID) => ["project", id] as const,
  releases: (p?: Params) => ["releases", p ?? {}] as const,
  release: (id: UUID) => ["release", id] as const,
  releaseTasks: (id: UUID) => ["release", id, "tasks"] as const,
  releaseSuggestion: (id: UUID) => ["release", id, "suggested-template"] as const,
  releaseBlockers: (id: UUID) => ["release", id, "blockers"] as const,
  tasks: (p?: Params) => ["tasks", p ?? {}] as const,
  task: (id: UUID) => ["task", id] as const,
  kanban: (p?: Params) => ["kanban", p ?? {}] as const,
  myWork: () => ["my-work"] as const,
  templates: (p?: Params) => ["templates", p ?? {}] as const,
  users: (p?: Params) => ["users", p ?? {}] as const,
  skills: () => ["skills"] as const,
  customers: () => ["customers"] as const,
  products: () => ["products"] as const,
  capacity: (p?: Params) => ["capacity", p ?? {}] as const,
  assignmentBoard: (p?: Params) => ["assignment-board", p ?? {}] as const,
  heatmap: (p?: Params) => ["heatmap", p ?? {}] as const,
  timeEntries: (p?: Params) => ["time-entries", p ?? {}] as const,
  runningTimer: () => ["running-timer"] as const,
  reviews: (p?: Params) => ["reviews", p ?? {}] as const,
  reviewQueue: () => ["review-queue"] as const,
  revisions: (p?: Params) => ["revisions", p ?? {}] as const,
  department: (p?: Params) => ["analytics", "department", p ?? {}] as const,
  trends: (months: number) => ["analytics", "trends", months] as const,
  insights: () => ["analytics", "insights"] as const,
  bottlenecks: () => ["analytics", "bottlenecks"] as const,
  dashboard: (role: string, p?: Params) => ["dashboard", role, p ?? {}] as const,
  projectDashboard: (id: UUID) => ["dashboard", "project", id] as const,
  userPerformance: (id: UUID, p?: Params) => ["performance", id, p ?? {}] as const,
  notifications: (p?: Params) => ["notifications", p ?? {}] as const,
  unreadCount: () => ["notifications", "unread"] as const,
};

/** Everything that can change when a task moves, so one call refreshes it all. */
function invalidateWorkflow(qc: ReturnType<typeof useQueryClient>) {
  for (const key of [
    "projects", "project", "releases", "release", "tasks", "task", "kanban",
    "my-work", "dashboard", "analytics", "capacity", "assignment-board",
    "heatmap", "reviews", "review-queue", "revisions", "time-entries",
    "running-timer", "notifications",
  ]) {
    qc.invalidateQueries({ queryKey: [key] });
  }
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export function useProjects(params?: Params) {
  return useQuery({
    queryKey: keys.projects(params),
    queryFn: () => get<Page<ProjectSummary>>("/api/projects", params),
  });
}

export function useProject(id: UUID | undefined) {
  return useQuery({
    queryKey: keys.project(id!),
    queryFn: () => get<ProjectDetail>(`/api/projects/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      post<ProjectDetail>("/api/projects", body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useUpdateProject(id: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      patch<ProjectDetail>(`/api/projects/${id}`, body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

// ---------------------------------------------------------------------------
// Releases
// ---------------------------------------------------------------------------

export function useReleases(params?: Params) {
  return useQuery({
    queryKey: keys.releases(params),
    queryFn: () => get<Page<ReleaseSummary>>("/api/releases", params),
  });
}

export function useRelease(id: UUID | undefined) {
  return useQuery({
    queryKey: keys.release(id!),
    queryFn: () => get<ReleaseDetail>(`/api/releases/${id}`),
    enabled: Boolean(id),
  });
}

export function useReleaseTasks(id: UUID | undefined) {
  return useQuery({
    queryKey: keys.releaseTasks(id!),
    queryFn: () => get<TaskSummary[]>(`/api/releases/${id}/tasks`),
    enabled: Boolean(id),
  });
}

export function useSuggestedTemplate(id: UUID | undefined) {
  return useQuery({
    queryKey: keys.releaseSuggestion(id!),
    queryFn: () => get<TemplateSuggestion>(`/api/releases/${id}/suggested-template`),
    enabled: Boolean(id),
  });
}

export function useCompletionBlockers(id: UUID | undefined) {
  return useQuery({
    queryKey: keys.releaseBlockers(id!),
    queryFn: () =>
      get<{ can_complete_cleanly: boolean; blocking_tasks: { code: string; name: string; status: string }[] }>(
        `/api/releases/${id}/completion-blockers`,
      ),
    enabled: Boolean(id),
  });
}

export function useCreateRelease() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      post<ReleaseDetail>("/api/releases", body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useApplyTemplate(releaseId: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (templateVersionId: UUID) =>
      post<TaskSummary[]>(`/api/releases/${releaseId}/apply-template`, {
        template_version_id: templateVersionId,
      }),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useAssignLead(releaseId: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (teamLeadId: UUID) =>
      post<ReleaseDetail>(`/api/releases/${releaseId}/assign-lead`, undefined, {
        team_lead_id: teamLeadId,
      }),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useAcceptRelease(releaseId: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => post<ReleaseDetail>(`/api/releases/${releaseId}/accept`),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useCompleteRelease(releaseId: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (overrideReason?: string) =>
      post<ReleaseDetail>(`/api/releases/${releaseId}/complete`, {
        override_reason: overrideReason ?? null,
      }),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

// ---------------------------------------------------------------------------
// Tasks
// ---------------------------------------------------------------------------

export function useTasks(params?: Params, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: keys.tasks(params),
    queryFn: () => get<Page<TaskSummary>>("/api/tasks", params),
    enabled: options?.enabled ?? true,
  });
}

export function useTask(id: UUID | undefined) {
  return useQuery({
    queryKey: keys.task(id!),
    queryFn: () => get<TaskDetail>(`/api/tasks/${id}`),
    enabled: Boolean(id),
  });
}

export function useKanban(params?: Params) {
  return useQuery({
    queryKey: keys.kanban(params),
    queryFn: () => get<KanbanBoard>("/api/tasks/kanban", params),
  });
}

export function useMyWork() {
  return useQuery({
    queryKey: keys.myWork(),
    queryFn: () => get<TaskSummary[]>("/api/tasks/my-work"),
  });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => post<TaskDetail>("/api/tasks", body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useUpdateTask(id: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      patch<TaskDetail>(`/api/tasks/${id}`, body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useAssignTask(id: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (assignedToId: UUID | null) =>
      post<TaskDetail>(`/api/tasks/${id}/assign`, { assigned_to_id: assignedToId }),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useEstimateTask(id: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { estimated_hours: number; reason?: string }) =>
      post<TaskDetail>(`/api/tasks/${id}/estimate`, body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useChangeTaskStatus(id: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { status: string; note?: string; delay_reason?: string }) =>
      post<TaskDetail>(`/api/tasks/${id}/status`, body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

/**
 * Status change where the task is part of the payload rather than baked into
 * the hook. The board needs this: a drop knows which card moved, but the
 * component's state has not committed yet, so a hook keyed on state would
 * mutate whichever task was selected previously.
 */
export function useMoveTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      taskId,
      ...body
    }: {
      taskId: UUID;
      status: string;
      note?: string;
      delay_reason?: string;
    }) => post<TaskDetail>(`/api/tasks/${taskId}/status`, body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useAddDependency(taskId: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { depends_on_task_id: UUID; is_blocking: boolean }) =>
      post(`/api/tasks/${taskId}/dependencies`, body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useRemoveDependency(taskId: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dependencyId: UUID) =>
      del(`/api/tasks/${taskId}/dependencies/${dependencyId}`),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

// ---------------------------------------------------------------------------
// Templates and catalog
// ---------------------------------------------------------------------------

export function useTemplates(params?: Params) {
  return useQuery({
    queryKey: keys.templates(params),
    queryFn: () => get<DesignTemplate[]>("/api/templates", params),
  });
}

export function useCustomers() {
  return useQuery({
    queryKey: keys.customers(),
    queryFn: () => get<Page<Customer>>("/api/customers", { page_size: 200 }),
    staleTime: 5 * 60_000,
  });
}

export function useProducts() {
  return useQuery({
    queryKey: keys.products(),
    queryFn: () => get<Product[]>("/api/products"),
    staleTime: 5 * 60_000,
  });
}

export function useProductFamilies() {
  return useQuery({
    queryKey: ["product-families"],
    queryFn: () => get<ProductFamily[]>("/api/product-families"),
    staleTime: 5 * 60_000,
  });
}

export function useSkills() {
  return useQuery({
    queryKey: keys.skills(),
    queryFn: () => get<Skill[]>("/api/skills"),
    staleTime: 5 * 60_000,
  });
}

export function useUsers(params?: Params) {
  return useQuery({
    queryKey: keys.users(params),
    queryFn: () => get<Page<User>>("/api/users", { page_size: 200, ...params }),
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// Resources
// ---------------------------------------------------------------------------

export function useCapacity(params?: Params, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: keys.capacity(params),
    queryFn: () => get<CapacitySummary[]>("/api/resources/capacity", params),
    enabled: options?.enabled ?? true,
  });
}

export function useMyCapacity(params?: Params) {
  return useQuery({
    queryKey: ["capacity", "me", params ?? {}],
    queryFn: () => get<CapacitySummary>("/api/resources/capacity/me", params),
  });
}

export function useAssignmentBoard(params?: Params, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: keys.assignmentBoard(params),
    queryFn: () => get<CapacitySummary[]>("/api/resources/assignment-board", params),
    enabled: options?.enabled ?? true,
  });
}

export function useHeatmap(params?: Params, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: keys.heatmap(params),
    queryFn: () =>
      get<{
        start: string;
        end: string;
        days: string[];
        thresholds: Record<string, number>;
        rows: {
          user_id: string;
          full_name: string;
          utilization_percent: number | null;
          utilization_band: string;
          cells: { date: string; available: number; allocated: number }[];
        }[];
      }>("/api/resources/heatmap", params),
    enabled: options?.enabled ?? true,
  });
}

// ---------------------------------------------------------------------------
// Time, reviews, revisions
// ---------------------------------------------------------------------------

export function useTimeEntries(params?: Params) {
  return useQuery({
    queryKey: keys.timeEntries(params),
    queryFn: () => get<Page<TimeEntry>>("/api/time/entries", params),
  });
}

export function useRunningTimer() {
  return useQuery({
    queryKey: keys.runningTimer(),
    queryFn: () => get<TimeEntry | null>("/api/time/running"),
    refetchInterval: 60_000,
  });
}

export function useStartTimer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { task_id: UUID; description?: string }) =>
      post<TimeEntry>("/api/time/start", body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useStopTimer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => post<TimeEntry>("/api/time/stop"),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useLogTime() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      post<TimeEntry>("/api/time/entries", body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useDeleteTimeEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: UUID) => del(`/api/time/entries/${id}`),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useReviews(params?: Params) {
  return useQuery({
    queryKey: keys.reviews(params),
    queryFn: () => get<Page<Review>>("/api/reviews", params),
  });
}

/**
 * The caller's own review queue.
 *
 * Gated on review.perform, which a Director and a Designer do not hold, so the
 * caller passes `enabled: false` rather than firing a request that can only
 * 403.
 */
export function useReviewQueue(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: keys.reviewQueue(),
    queryFn: () => get<Review[]>("/api/reviews/queue"),
    enabled: options?.enabled ?? true,
  });
}

export function useSubmitForReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { task_id: UUID; reviewer_id?: UUID; note?: string; delay_reason?: string }) =>
      post<Review>("/api/reviews/submit", body),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useStartReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: UUID) => post<Review>(`/api/reviews/${id}/start`),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useReviewDecision(reviewId: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      post<{ review: Review; revision: Revision | null }>(
        `/api/reviews/${reviewId}/decision`,
        body,
      ),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

export function useRevisions(params?: Params) {
  return useQuery({
    queryKey: keys.revisions(params),
    queryFn: () => get<Page<Revision>>("/api/revisions", params),
  });
}

/**
 * Every configured vocabulary a form needs, in one authenticated call.
 *
 * Screens populate their selects from this rather than hardcoding values. The
 * lists are runtime-editable and nothing server-side rejects an unknown
 * string, so an invented value does not error -- it silently drifts. For a
 * revision category that is worse than drift: accountability_for() falls back
 * to "Controllable", booking the rework against the team that raised it.
 */
export interface Vocabularies {
  delay_reasons: { value: string; accountability: string }[];
  revision_categories: { value: string; accountability: string }[];
  task_types: string[];
  release_types: string[];
  project_types: string[];
  require_delay_reason: boolean;
  capacity_thresholds: Record<string, number>;
}

export function useVocabularies() {
  return useQuery({
    queryKey: ["vocabularies"],
    queryFn: () => get<Vocabularies>("/api/meta/vocabularies"),
    staleTime: 10 * 60_000,
  });
}

/**
 * Delay reasons, readable by anyone. Blocking a task or submitting a late one
 * requires choosing from this list, so it is deliberately not behind the
 * settings permission -- otherwise a designer could not complete a form the
 * API insists they fill in.
 */
export function useDelayReasons() {
  return useQuery({
    queryKey: ["delay-reasons"],
    queryFn: () =>
      get<{ value: string; accountability: string }[]>("/api/tasks/delay-reasons"),
    staleTime: 10 * 60_000,
  });
}

export function useRevisionCategories() {
  return useQuery({
    queryKey: ["revision-categories"],
    queryFn: () =>
      get<{ value: string; accountability: string }[]>("/api/revisions/categories"),
    staleTime: 10 * 60_000,
  });
}

export function useResolveRevision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: UUID) => post<Revision>(`/api/revisions/${id}/resolve`),
    onSuccess: () => invalidateWorkflow(qc),
  });
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export function useDepartmentMetrics(params?: Params) {
  return useQuery({
    queryKey: keys.department(params),
    queryFn: () => get<DepartmentMetrics>("/api/analytics/department", params),
  });
}

export function useTrends(months = 6) {
  return useQuery({
    queryKey: keys.trends(months),
    queryFn: () => get<MonthlyTrend[]>("/api/analytics/trends", { months }),
  });
}

export function useInsights() {
  return useQuery({
    queryKey: keys.insights(),
    queryFn: () => get<Insight[]>("/api/analytics/insights"),
  });
}

export function useDashboard<T>(
  role: "executive" | "manager" | "team-lead" | "designer",
  params?: Params,
  options?: Partial<UseQueryOptions<T>>,
) {
  return useQuery<T>({
    queryKey: keys.dashboard(role, params),
    queryFn: () => get<T>(`/api/analytics/dashboard/${role}`, params),
    ...options,
  });
}

export function useProjectDashboard(id: UUID | undefined) {
  return useQuery({
    queryKey: keys.projectDashboard(id!),
    queryFn: () => get<Record<string, any>>(`/api/analytics/projects/${id}`),
    enabled: Boolean(id),
  });
}

export function useUserPerformance(id: UUID | undefined, params?: Params) {
  return useQuery({
    queryKey: keys.userPerformance(id!, params),
    queryFn: () => get<DesignerMetrics>(`/api/analytics/users/${id}`, params),
    enabled: Boolean(id),
  });
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export function useNotifications(params?: Params) {
  return useQuery({
    queryKey: keys.notifications(params),
    queryFn: () => get<Page<Notification>>("/api/notifications", params),
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: keys.unreadCount(),
    queryFn: () => get<{ unread: number }>("/api/notifications/unread-count"),
    refetchInterval: 60_000,
  });
}

export function useMarkNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: UUID[]) =>
      post("/api/notifications/mark-read", { notification_ids: ids }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => post("/api/notifications/mark-all-read"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export function useSettings(category?: string) {
  return useQuery({
    queryKey: ["settings", category ?? "all"],
    queryFn: () =>
      get<{ id: UUID; key: string; category: string; value: unknown; description: string | null }[]>(
        "/api/settings",
        { category },
      ),
  });
}

export function useUpdateSetting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      put(`/api/settings/${key}`, { value }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      // The vocabularies are cached for ten minutes; without this an edited
      // delay-reason list keeps offering values that no longer exist.
      qc.invalidateQueries({ queryKey: ["delay-reasons"] });
      qc.invalidateQueries({ queryKey: ["vocabularies"] });
      qc.invalidateQueries({ queryKey: ["revision-categories"] });
      invalidateWorkflow(qc);
    },
  });
}

// ---------------------------------------------------------------------------
// Template authoring
// ---------------------------------------------------------------------------

/**
 * Publishing or editing a template changes more than the template list: the
 * per-release suggestion and the create-release matcher both read only
 * published versions, so a freshly published template must invalidate them or
 * a release keeps reporting "no template matches" until the cache goes stale.
 */
function invalidateTemplates(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["templates"] });
  qc.invalidateQueries({ queryKey: ["template-match"] });
  qc.invalidateQueries({ queryKey: ["release"] });
}

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      post<DesignTemplate>("/api/templates", body),
    onSuccess: () => invalidateTemplates(qc),
  });
}

export function useCreateDraft(templateId: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (changeNote: string) =>
      post(`/api/templates/${templateId}/versions`, { change_note: changeNote }),
    onSuccess: () => invalidateTemplates(qc),
  });
}

export function useSaveVersionTasks(versionId: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tasks: Record<string, unknown>[]) =>
      put(`/api/templates/versions/${versionId}/tasks`, tasks),
    onSuccess: () => invalidateTemplates(qc),
  });
}

export function usePublishVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (versionId: UUID) =>
      post(`/api/templates/versions/${versionId}/publish`),
    onSuccess: () => invalidateTemplates(qc),
  });
}
