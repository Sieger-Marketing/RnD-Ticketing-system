"""Project, design release, template and task payloads."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.enums import Priority, ReleaseStatus, TaskStatus
from app.schemas.common import ORMModel

# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    description: str | None = None
    customer_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    project_type: str | None = None
    sales_order: str | None = None
    work_order: str | None = None
    project_manager_id: uuid.UUID | None = None
    design_manager_id: uuid.UUID | None = None
    priority: str = Priority.MEDIUM.value
    start_date: date | None = None
    required_completion_date: date | None = None
    internal_deadline: date | None = None
    customer_deadline: date | None = None
    external_id: str | None = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> "ProjectCreate":
        if (
            self.start_date
            and self.required_completion_date
            and self.required_completion_date < self.start_date
        ):
            raise ValueError("required_completion_date cannot be before start_date")
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=240)
    description: str | None = None
    customer_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    project_type: str | None = None
    sales_order: str | None = None
    work_order: str | None = None
    project_manager_id: uuid.UUID | None = None
    design_manager_id: uuid.UUID | None = None
    priority: str | None = None
    status: str | None = None
    start_date: date | None = None
    required_completion_date: date | None = None
    internal_deadline: date | None = None
    customer_deadline: date | None = None
    external_id: str | None = None


class ProjectSummary(ORMModel):
    """Row shape for project lists and the pipeline chart."""

    id: uuid.UUID
    code: str
    name: str
    # The ids travel with the names so an edit form or a release's template
    # lookup can inherit the project's customer and product without a second
    # round trip.
    customer_id: uuid.UUID | None = None
    customer_name: str | None = None
    product_id: uuid.UUID | None = None
    product_name: str | None = None
    project_type: str | None = None
    priority: str
    status: str
    health: str
    completion_percent: float
    planned_hours: float
    actual_hours: float
    rework_hours: float
    delay_days: int
    revision_count: int
    start_date: date | None = None
    required_completion_date: date | None = None
    design_manager_name: str | None = None
    release_count: int = 0
    task_count: int = 0
    #: Car spaces the system provides, and the date the drawings are good for
    #: construction. Both come off the design team's own tracker and are the
    #: first things anyone asks about a parking project.
    car_count: int | None = None
    gfc_date: date | None = None

    @classmethod
    def from_model(cls, p, release_count: int = 0, task_count: int = 0) -> "ProjectSummary":
        return cls(
            id=p.id,
            code=p.code,
            name=p.name,
            customer_id=p.customer_id,
            customer_name=p.customer.name if p.customer else None,
            product_id=p.product_id,
            product_name=p.product.name if p.product else None,
            project_type=p.project_type,
            priority=p.priority,
            status=p.status,
            health=p.health,
            completion_percent=float(p.completion_percent or 0),
            planned_hours=float(p.planned_hours or 0),
            actual_hours=float(p.actual_hours or 0),
            rework_hours=float(p.rework_hours or 0),
            delay_days=p.delay_days or 0,
            revision_count=p.revision_count or 0,
            start_date=p.start_date,
            required_completion_date=p.required_completion_date,
            design_manager_name=p.design_manager.full_name if p.design_manager else None,
            release_count=release_count,
            task_count=task_count,
            car_count=p.car_count,
            gfc_date=p.gfc_date,
        )


class ProjectDetail(ProjectSummary):
    description: str | None = None
    sales_order: str | None = None
    work_order: str | None = None
    internal_deadline: date | None = None
    customer_deadline: date | None = None
    actual_completion_date: date | None = None
    health_reasons: list[dict] = []
    external_id: str | None = None
    created_at: datetime
    updated_at: datetime
    efficiency_percent: float | None = None
    effort_variance: float | None = None


# ---------------------------------------------------------------------------
# Design releases
# ---------------------------------------------------------------------------


class ReleaseCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=240)
    release_type: str = Field(min_length=1, max_length=80)
    description: str | None = None
    sequence_number: int | None = Field(None, gt=0)
    product_id: uuid.UUID | None = None
    team_lead_id: uuid.UUID | None = None
    priority: str = Priority.MEDIUM.value
    planned_start: date | None = None
    planned_end: date | None = None
    #: When set, the release's standard tasks are generated immediately.
    template_version_id: uuid.UUID | None = None
    external_id: str | None = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> "ReleaseCreate":
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("planned_end cannot be before planned_start")
        return self


class ReleaseUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=240)
    release_type: str | None = None
    description: str | None = None
    team_lead_id: uuid.UUID | None = None
    priority: str | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    delay_reason: str | None = None
    delay_note: str | None = None
    external_id: str | None = None


class ReleaseSummary(ORMModel):
    id: uuid.UUID
    code: str
    project_id: uuid.UUID
    project_code: str | None = None
    project_name: str | None = None
    sequence_number: int
    name: str
    release_type: str
    priority: str
    status: str
    review_status: str
    health: str
    completion_percent: float
    estimated_hours: float
    actual_hours: float
    rework_hours: float
    revision_count: int
    delay_days: int
    planned_start: date | None = None
    planned_end: date | None = None
    team_lead_id: uuid.UUID | None = None
    team_lead_name: str | None = None
    task_count: int = 0
    #: How many of this system the project takes.
    unit_count: int | None = None

    @classmethod
    def from_model(cls, r, task_count: int = 0) -> "ReleaseSummary":
        return cls(
            id=r.id,
            code=r.code,
            project_id=r.project_id,
            project_code=r.project.code if r.project else None,
            project_name=r.project.name if r.project else None,
            sequence_number=r.sequence_number,
            name=r.name,
            release_type=r.release_type,
            priority=r.priority,
            status=r.status,
            review_status=r.review_status,
            health=r.health,
            completion_percent=float(r.completion_percent or 0),
            estimated_hours=float(r.estimated_hours or 0),
            actual_hours=float(r.actual_hours or 0),
            rework_hours=float(r.rework_hours or 0),
            revision_count=r.revision_count or 0,
            delay_days=r.delay_days or 0,
            planned_start=r.planned_start,
            planned_end=r.planned_end,
            team_lead_id=r.team_lead_id,
            team_lead_name=r.team_lead.full_name if r.team_lead else None,
            task_count=task_count,
            unit_count=r.unit_count,
        )


class ReleaseDetail(ReleaseSummary):
    description: str | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    #: What was originally committed. planned_start/planned_end are the current
    #: forecast and may have moved; these have not.
    baseline_planned_start: date | None = None
    baseline_planned_end: date | None = None
    health_reasons: list[dict] = []
    template_version_id: uuid.UUID | None = None
    template_name: str | None = None
    template_version_label: str | None = None
    delay_reason: str | None = None
    delay_note: str | None = None
    completion_override_reason: str | None = None
    efficiency_percent: float | None = None
    effort_variance: float | None = None
    external_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ReleaseStatusChange(BaseModel):
    status: str
    note: str | None = None

    @field_validator("status")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in {s.value for s in ReleaseStatus}:
            raise ValueError(f"unknown release status '{value}'")
        return value


class ReleaseComplete(BaseModel):
    #: Required only when mandatory tasks are still open; the server refuses
    #: the completion otherwise rather than accepting a silent override.
    override_reason: str | None = None


class ApplyTemplate(BaseModel):
    template_version_id: uuid.UUID


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TemplateTaskIn(BaseModel):
    sequence: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=240)
    task_type: str = Field(min_length=1, max_length=80)
    description: str | None = None
    default_estimated_hours: float = Field(0, ge=0, le=1000)
    default_priority: str = Priority.MEDIUM.value
    complexity: int = Field(3, ge=1, le=5)
    required_skill_id: uuid.UUID | None = None
    is_mandatory: bool = True
    requires_review: bool = True
    depends_on_sequence: int | None = Field(None, gt=0)
    #: False makes the prerequisite advisory: the dependency is still
    #: recorded and shown, but it does not prevent the task starting.
    depends_on_blocking: bool = True


class TemplateTaskOut(TemplateTaskIn):
    id: uuid.UUID
    required_skill_name: str | None = None

    model_config = {"from_attributes": True}


class TemplateVersionOut(ORMModel):
    id: uuid.UUID
    version_number: int
    label: str
    is_published: bool
    published_at: datetime | None = None
    change_note: str | None = None
    task_count: int = 0
    total_estimated_hours: float = 0
    tasks: list[TemplateTaskOut] = []


class TemplateOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    release_type: str
    product_id: uuid.UUID | None = None
    product_name: str | None = None
    product_family_id: uuid.UUID | None = None
    product_family_name: str | None = None
    is_active: bool
    current_version_number: int | None = None
    versions: list[TemplateVersionOut] = []


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    release_type: str = Field(min_length=1, max_length=80)
    description: str | None = None
    product_id: uuid.UUID | None = None
    product_family_id: uuid.UUID | None = None
    tasks: list[TemplateTaskIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _needs_a_target(self) -> "TemplateCreate":
        if not self.product_id and not self.product_family_id:
            raise ValueError(
                "a template must target either a product or a product family"
            )
        return self


class DraftVersionCreate(BaseModel):
    change_note: str | None = None


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


class TaskCreate(BaseModel):
    release_id: uuid.UUID
    name: str = Field(min_length=1, max_length=240)
    task_type: str = Field(min_length=1, max_length=80)
    description: str | None = None
    sequence: int | None = Field(None, gt=0)
    assigned_to_id: uuid.UUID | None = None
    required_skill_id: uuid.UUID | None = None
    priority: str = Priority.MEDIUM.value
    complexity: int = Field(3, ge=1, le=5)
    is_mandatory: bool = True
    requires_review: bool = True
    planned_start: date | None = None
    planned_end: date | None = None
    estimated_hours: float = Field(0, ge=0, le=1000)
    depends_on_task_ids: list[uuid.UUID] = Field(default_factory=list)
    external_id: str | None = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> "TaskCreate":
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("planned_end cannot be before planned_start")
        return self


class TaskUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=240)
    description: str | None = None
    task_type: str | None = None
    priority: str | None = None
    complexity: int | None = Field(None, ge=1, le=5)
    is_mandatory: bool | None = None
    requires_review: bool | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    delay_reason: str | None = None
    delay_note: str | None = None
    external_id: str | None = None


class TaskAssign(BaseModel):
    assigned_to_id: uuid.UUID | None = None


class TaskEstimate(BaseModel):
    estimated_hours: float = Field(ge=0, le=1000)
    reason: str | None = None


class TaskStatusChange(BaseModel):
    status: str
    note: str | None = None
    delay_reason: str | None = None
    #: Required when moving to On Hold: a pause nobody explained is
    #: indistinguishable later from work that was forgotten.
    hold_reason: str | None = None
    #: Required when finishing work whose hours drifted materially from the
    #: estimate. Captured now, because asking a week later produces "not sure".
    variance_reason: str | None = None
    variance_note: str | None = None

    @field_validator("status")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in {s.value for s in TaskStatus}:
            raise ValueError(f"unknown task status '{value}'")
        return value


class DependencyIn(BaseModel):
    depends_on_task_id: uuid.UUID
    is_blocking: bool = True


class DependencyOut(BaseModel):
    id: uuid.UUID
    depends_on_task_id: uuid.UUID
    depends_on_code: str | None = None
    depends_on_name: str | None = None
    depends_on_status: str | None = None
    dependency_type: str
    is_blocking: bool
    is_satisfied: bool


class TaskSummary(ORMModel):
    id: uuid.UUID
    code: str
    project_id: uuid.UUID
    project_code: str | None = None
    release_id: uuid.UUID
    release_code: str | None = None
    name: str
    task_type: str
    status: str
    review_status: str
    priority: str
    complexity: int
    is_mandatory: bool
    requires_review: bool
    completion_percent: float
    estimated_hours: float
    actual_hours: float
    rework_hours: float
    revision_count: int
    delay_days: int
    is_overdue: bool = False
    planned_start: date | None = None
    planned_end: date | None = None
    assigned_to_id: uuid.UUID | None = None
    assigned_to_name: str | None = None
    required_skill_name: str | None = None
    blocker_reason: str | None = None


class TaskDetail(TaskSummary):
    hold_reason: str | None = None
    hold_note: str | None = None
    variance_reason: str | None = None
    variance_note: str | None = None
    description: str | None = None
    sequence: int
    team_lead_id: uuid.UUID | None = None
    original_estimated_hours: float
    blocked_hours: float
    submission_count: int
    delay_reason: str | None = None
    delay_note: str | None = None
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    external_id: str | None = None
    efficiency_percent: float | None = None
    effort_variance: float | None = None
    cycle_time_hours: float | None = None
    queue_time_hours: float | None = None
    dependencies: list[DependencyOut] = []
    blocked_by: list[DependencyOut] = []
    can_start: bool = True
    allowed_transitions: list[str] = []


class KanbanColumn(BaseModel):
    key: str
    title: str
    statuses: list[str]
    count: int
    tasks: list[TaskSummary]


class KanbanBoard(BaseModel):
    columns: list[KanbanColumn]
    total: int
