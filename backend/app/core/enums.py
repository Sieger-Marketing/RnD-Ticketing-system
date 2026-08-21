"""Domain vocabularies.

These are the values the workflow state machine reasons about, so they live in
code rather than in a settings table. Everything an operations manager is
expected to tune at runtime -- capacity thresholds, KPI weights, delay reasons,
revision categories, priorities -- lives in the `app_settings` table instead
(see app/services/settings_service.py), per spec sections 34 and 12.
"""

from enum import Enum


class StrEnum(str, Enum):
    """String-valued enum that serialises as its value."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------
class RoleName(StrEnum):
    ADMINISTRATOR = "Administrator"
    DIRECTOR = "Director"
    DESIGN_MANAGER = "Design Manager"
    TEAM_LEAD = "Team Lead"
    DESIGNER = "Designer"


class SkillLevel(StrEnum):
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"
    EXPERT = "Expert"


# ---------------------------------------------------------------------------
# Workflow states
# ---------------------------------------------------------------------------
class ProjectStatus(StrEnum):
    NOT_STARTED = "Not Started"
    PLANNING = "Planning"
    DESIGN_IN_PROGRESS = "Design In Progress"
    INTERNAL_REVIEW = "Internal Review"
    CUSTOMER_REVIEW = "Customer Review"
    REVISION = "Revision"
    APPROVED = "Approved"
    COMPLETED = "Completed"
    ON_HOLD = "On Hold"
    CANCELLED = "Cancelled"


class ReleaseStatus(StrEnum):
    DRAFT = "Draft"
    ASSIGNED = "Assigned"
    PLANNING = "Planning"
    IN_PROGRESS = "In Progress"
    INTERNAL_REVIEW = "Internal Review"
    REVISION = "Revision"
    APPROVED = "Approved"
    COMPLETED = "Completed"
    ON_HOLD = "On Hold"
    CANCELLED = "Cancelled"


class TaskStatus(StrEnum):
    NOT_STARTED = "Not Started"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    SUBMITTED_FOR_REVIEW = "Submitted for Review"
    UNDER_REVIEW = "Under Review"
    REVISION_REQUIRED = "Revision Required"
    APPROVED = "Approved"
    COMPLETED = "Completed"
    ON_HOLD = "On Hold"
    CANCELLED = "Cancelled"


#: Terminal states never re-enter the working set.
TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.CANCELLED}

#: Statuses that mean a task still owes work, used by the delay engine.
OPEN_TASK_STATUSES = {
    TaskStatus.NOT_STARTED,
    TaskStatus.ASSIGNED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.BLOCKED,
    TaskStatus.SUBMITTED_FOR_REVIEW,
    TaskStatus.UNDER_REVIEW,
    TaskStatus.REVISION_REQUIRED,
}

#: Kanban columns (spec section 10). Several statuses collapse into one column.
KANBAN_COLUMNS: dict[str, list[TaskStatus]] = {
    "Not Started": [TaskStatus.NOT_STARTED],
    "Assigned": [TaskStatus.ASSIGNED],
    "In Progress": [TaskStatus.IN_PROGRESS],
    "Blocked": [TaskStatus.BLOCKED],
    "Review": [TaskStatus.SUBMITTED_FOR_REVIEW, TaskStatus.UNDER_REVIEW],
    "Revision": [TaskStatus.REVISION_REQUIRED],
    "Completed": [TaskStatus.APPROVED, TaskStatus.COMPLETED],
}


class ReviewStatus(StrEnum):
    NOT_SUBMITTED = "Not Submitted"
    PENDING = "Pending"
    IN_REVIEW = "In Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    REVISION_REQUESTED = "Revision Requested"


class ReviewResult(StrEnum):
    APPROVED = "Approved"
    REJECTED = "Rejected"
    REVISION_REQUESTED = "Revision Requested"


class RevisionStatus(StrEnum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    CANCELLED = "Cancelled"


class HealthStatus(StrEnum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class Priority(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


#: Effort weighting for the performance engine. Criticality matters when
#: normalising output (spec section 48).
PRIORITY_WEIGHT: dict[str, float] = {
    Priority.LOW: 0.8,
    Priority.MEDIUM: 1.0,
    Priority.HIGH: 1.25,
    Priority.CRITICAL: 1.5,
}


class DependencyType(StrEnum):
    FINISH_TO_START = "Finish to Start"
    START_TO_START = "Start to Start"
    FINISH_TO_FINISH = "Finish to Finish"


class TimeEntrySource(StrEnum):
    TIMER = "Timer"
    MANUAL = "Manual"


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
class Accountability(StrEnum):
    """Whether the department could have prevented it.

    Drives fair performance evaluation: a designer is not penalised for a
    customer-driven change (spec sections 16 and 20).
    """

    CONTROLLABLE = "Controllable"
    EXTERNAL = "External"


class NotificationSeverity(StrEnum):
    INFO = "Info"
    WARNING = "Warning"
    CRITICAL = "Critical"


class SyncDirection(StrEnum):
    INBOUND = "Inbound"
    OUTBOUND = "Outbound"
    BIDIRECTIONAL = "Bidirectional"


class SyncStatus(StrEnum):
    PENDING = "Pending"
    SYNCED = "Synced"
    FAILED = "Failed"
    SKIPPED = "Skipped"


class AuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    STATUS_CHANGE = "STATUS_CHANGE"
    ASSIGN = "ASSIGN"
    OVERRIDE = "OVERRIDE"
    LOGIN = "LOGIN"
