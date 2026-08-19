"""Template matching and task generation (spec sections 9 and 47 steps 3-5).

Generating a release's tasks from a template is the step that turns a product
choice into concrete work. Two rules make it safe to evolve templates over
time:

* A release pins the template *version* it was generated from, so publishing
  v3 never rewrites releases built from v2.
* Published versions are immutable. Editing means creating a new draft.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, ReleaseStatus, TaskStatus
from app.core.errors import BusinessRuleError, NotFoundError
from app.models.release import DesignRelease
from app.models.task import Task, TaskDependency
from app.models.template import DesignTemplate, DesignTemplateVersion, TemplateTask
from app.models.user import User
from app.services import audit_service, code_service, settings_service


def find_matching_templates(
    db: Session,
    *,
    product_id: uuid.UUID | None,
    product_family_id: uuid.UUID | None,
    release_type: str,
) -> list[DesignTemplate]:
    """Templates that fit this product and release type, best match first.

    A product-specific template outranks a family-wide one, so a family
    default can exist without overriding a product that has its own.
    """
    stmt = select(DesignTemplate).where(
        DesignTemplate.is_active.is_(True),
        DesignTemplate.release_type == release_type,
    )
    candidates = db.execute(stmt).scalars().all()

    def rank(template: DesignTemplate) -> int:
        if product_id and template.product_id == product_id:
            return 0
        if product_family_id and template.product_family_id == product_family_id:
            return 1
        return 2

    matches = [
        t
        for t in candidates
        if (product_id and t.product_id == product_id)
        or (product_family_id and t.product_family_id == product_family_id)
    ]
    return sorted(matches, key=rank)


def suggest_template(
    db: Session,
    *,
    product_id: uuid.UUID | None,
    product_family_id: uuid.UUID | None,
    release_type: str,
) -> DesignTemplateVersion | None:
    """The published version the system would apply by default."""
    for template in find_matching_templates(
        db,
        product_id=product_id,
        product_family_id=product_family_id,
        release_type=release_type,
    ):
        version = template.current_version
        if version is not None:
            return version
    return None


def create_draft_version(
    db: Session, template: DesignTemplate, *, actor: User | None, change_note: str | None
) -> DesignTemplateVersion:
    """Open a new draft, copying the current published version's tasks.

    Editing an already-published version is refused elsewhere; this is the
    supported way to change a template.
    """
    existing_draft = next((v for v in template.versions if not v.is_published), None)
    if existing_draft is not None:
        raise BusinessRuleError(
            f"Template {template.code} already has an unpublished draft "
            f"(v{existing_draft.version_number}). Publish or discard it first."
        )

    next_number = max((v.version_number for v in template.versions), default=0) + 1
    draft = DesignTemplateVersion(
        template_id=template.id,
        version_number=next_number,
        is_published=False,
        change_note=change_note,
    )
    db.add(draft)
    db.flush()

    source = template.current_version
    if source is not None:
        for task in source.tasks:
            db.add(
                TemplateTask(
                    version_id=draft.id,
                    sequence=task.sequence,
                    name=task.name,
                    task_type=task.task_type,
                    description=task.description,
                    default_estimated_hours=task.default_estimated_hours,
                    default_priority=task.default_priority,
                    complexity=task.complexity,
                    required_skill_id=task.required_skill_id,
                    is_mandatory=task.is_mandatory,
                    requires_review=task.requires_review,
                    depends_on_sequence=task.depends_on_sequence,
                    # Easy to forget, and forgetting it silently re-gates every
                    # dependency the previous version had deliberately relaxed.
                    depends_on_blocking=task.depends_on_blocking,
                )
            )
        db.flush()

    audit_service.record(
        db,
        entity_type="design_template",
        entity_id=template.id,
        entity_code=template.code,
        action=AuditAction.CREATE,
        actor=actor,
        summary=f"Opened draft v{next_number}",
    )
    return draft


def publish_version(
    db: Session, version: DesignTemplateVersion, *, actor: User | None
) -> DesignTemplateVersion:
    from datetime import UTC, datetime

    if version.is_published:
        raise BusinessRuleError("This template version is already published.")
    if not version.tasks:
        raise BusinessRuleError("A template version must contain at least one task.")

    version.is_published = True
    version.published_at = datetime.now(UTC)
    version.published_by_id = actor.id if actor else None
    db.flush()

    audit_service.record(
        db,
        entity_type="design_template_version",
        entity_id=version.id,
        action=AuditAction.UPDATE,
        actor=actor,
        summary=f"Published v{version.version_number} "
        f"with {len(version.tasks)} standard task(s)",
    )
    return version


def generate_tasks_for_release(
    db: Session,
    release: DesignRelease,
    version: DesignTemplateVersion,
    *,
    actor: User | None,
    context: dict | None = None,
) -> list[Task]:
    """Create the release's standard tasks from a template version.

    Refuses to run twice: a release that already has tasks must have them
    edited, not silently duplicated. Template `depends_on_sequence` values are
    resolved into real dependency rows so the sequencing survives generation.
    """
    if not version.is_published:
        raise BusinessRuleError(
            "Only a published template version can be applied to a release."
        )

    existing = db.execute(
        select(Task.id).where(Task.release_id == release.id).limit(1)
    ).first()
    if existing:
        raise BusinessRuleError(
            f"Release {release.code} already has tasks. Add or edit them "
            "individually instead of regenerating."
        )

    work_days = settings_service.working_days(db)
    start = release.planned_start or date.today()

    created: list[Task] = []
    by_sequence: dict[int, Task] = {}
    cursor = start

    for template_task in sorted(version.tasks, key=lambda t: t.sequence):
        estimated = float(template_task.default_estimated_hours or 0)
        # Schedule sequentially at 8 productive hours a day, skipping
        # non-working days. The Team Lead re-plans afterwards; this only has
        # to be a sane starting point rather than a final schedule.
        span_days = max(int(round(estimated / 8.0)), 1)
        task_start = _next_working_day(cursor, work_days)
        task_end = _add_working_days(task_start, span_days - 1, work_days)

        task = Task(
            code=code_service.next_code(db, "task"),
            project_id=release.project_id,
            release_id=release.id,
            template_task_id=template_task.id,
            name=template_task.name,
            description=template_task.description,
            task_type=template_task.task_type,
            sequence=template_task.sequence,
            team_lead_id=release.team_lead_id,
            required_skill_id=template_task.required_skill_id,
            priority=template_task.default_priority,
            complexity=template_task.complexity,
            is_mandatory=template_task.is_mandatory,
            requires_review=template_task.requires_review,
            planned_start=task_start,
            planned_end=task_end,
            original_estimated_hours=estimated,
            estimated_hours=estimated,
            status=TaskStatus.NOT_STARTED.value,
            created_by_id=actor.id if actor else None,
        )
        db.add(task)
        db.flush()

        created.append(task)
        by_sequence[template_task.sequence] = task
        cursor = _add_working_days(task_end, 1, work_days)

    for template_task in sorted(version.tasks, key=lambda t: t.sequence):
        if template_task.depends_on_sequence is None:
            continue
        child = by_sequence.get(template_task.sequence)
        parent = by_sequence.get(template_task.depends_on_sequence)
        if child is None or parent is None or child.id == parent.id:
            continue
        db.add(
            TaskDependency(
                task_id=child.id,
                depends_on_task_id=parent.id,
                # Carried from the template rather than forced. An advisory
                # link still shows the intended order on the task screen; it
                # just does not refuse the start.
                is_blocking=template_task.depends_on_blocking,
            )
        )

    release.template_version_id = version.id
    if release.status == ReleaseStatus.DRAFT.value:
        release.status = ReleaseStatus.PLANNING.value
    db.flush()

    audit_service.record(
        db,
        entity_type="design_release",
        entity_id=release.id,
        entity_code=release.code,
        action=AuditAction.CREATE,
        actor=actor,
        summary=f"Generated {len(created)} task(s) from "
        f"{version.template.name} v{version.version_number}",
        new_value={
            "template_version_id": str(version.id),
            "task_codes": [t.code for t in created],
        },
        context=context,
    )
    return created


def _next_working_day(day: date, work_days: set[int]) -> date:
    guard = 0
    while day.weekday() not in work_days and guard < 14:
        day += timedelta(days=1)
        guard += 1
    return day


def _add_working_days(start: date, days: int, work_days: set[int]) -> date:
    current = _next_working_day(start, work_days)
    remaining = days
    guard = 0
    while remaining > 0 and guard < 400:
        current += timedelta(days=1)
        if current.weekday() in work_days:
            remaining -= 1
        guard += 1
    return current


def get_version_or_404(db: Session, version_id: uuid.UUID) -> DesignTemplateVersion:
    version = db.get(DesignTemplateVersion, version_id)
    if version is None:
        raise NotFoundError("Template version not found.")
    return version
