/**
 * Fixed vocabularies, mirroring backend app/core/enums.py.
 *
 * These are workflow states, not tunable business rules -- adding a status
 * means changing the state machine, so it belongs in code. Anything the
 * Manager is meant to configure (capacity bands, KPI weights, delay reasons)
 * is read from the settings API instead of being listed here.
 */

import type { Health, Priority, ProjectStatus, ReleaseStatus, TaskStatus } from "@/types/api";

export const PRIORITIES: Priority[] = ["Low", "Medium", "High", "Critical"];

export const HEALTH_LEVELS: Health[] = ["GREEN", "AMBER", "RED"];

export const PROJECT_STATUSES: ProjectStatus[] = [
  "Not Started",
  "Planning",
  "Design In Progress",
  "Internal Review",
  "Customer Review",
  "Revision",
  "Approved",
  "Completed",
  "On Hold",
  "Cancelled",
];

export const RELEASE_STATUSES: ReleaseStatus[] = [
  "Draft",
  "Assigned",
  "Planning",
  "In Progress",
  "Internal Review",
  "Revision",
  "Approved",
  "Completed",
  "On Hold",
  "Cancelled",
];

export const TASK_STATUSES: TaskStatus[] = [
  "Not Started",
  "Assigned",
  "In Progress",
  "Blocked",
  "Submitted for Review",
  "Under Review",
  "Revision Required",
  "Approved",
  "Completed",
  "Cancelled",
];

/** Statuses that mean the work is still live. */
export const OPEN_PROJECT_STATUSES: ProjectStatus[] = [
  "Not Started",
  "Planning",
  "Design In Progress",
  "Internal Review",
  "Customer Review",
  "Revision",
];

export const toOptions = (values: readonly string[]) =>
  values.map((value) => ({ value, label: value }));
