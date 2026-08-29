"""Time entry, review, revision and supporting payloads."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.enums import ReviewResult
from app.schemas.common import ORMModel

# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


class TimerStart(BaseModel):
    task_id: uuid.UUID
    description: str | None = None


class TimeEntryCreate(BaseModel):
    task_id: uuid.UUID
    entry_date: date
    hours: float = Field(gt=0, le=16)
    description: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    #: Managers correcting someone else's sheet; defaults to the caller.
    user_id: uuid.UUID | None = None

    @field_validator("entry_date")
    @classmethod
    def _not_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("time cannot be logged against a future date")
        return value


class TimeEntryOut(ORMModel):
    id: uuid.UUID
    code: str
    task_id: uuid.UUID
    task_code: str | None = None
    task_name: str | None = None
    user_id: uuid.UUID
    user_name: str | None = None
    project_id: uuid.UUID | None = None
    #: A timesheet row that says TSK-002052 asks the reader to hold a code table
    #: in their head. "Kumaran Medical Centre / Structures" is what they booked
    #: the time against.
    project_name: str | None = None
    release_id: uuid.UUID | None = None
    release_name: str | None = None
    entry_date: date
    started_at: datetime | None = None
    ended_at: datetime | None = None
    hours: float
    source: str
    is_running: bool
    is_rework: bool
    revision_id: uuid.UUID | None = None
    description: str | None = None

    @classmethod
    def from_model(cls, e) -> "TimeEntryOut":
        return cls(
            id=e.id,
            code=e.code,
            task_id=e.task_id,
            task_code=e.task.code if e.task else None,
            task_name=e.task.name if e.task else None,
            user_id=e.user_id,
            user_name=e.user.full_name if e.user else None,
            project_id=e.project_id,
            # Read through the task rather than off the entry: the entry stores
            # the ids for reporting, but only the task carries the objects.
            project_name=(
                e.task.project.name if e.task and e.task.project else None
            ),
            release_id=e.release_id,
            release_name=(
                e.task.release.name if e.task and e.task.release else None
            ),
            entry_date=e.entry_date,
            started_at=e.started_at,
            ended_at=e.ended_at,
            hours=float(e.hours or 0),
            source=e.source,
            is_running=e.is_running,
            is_rework=e.is_rework,
            revision_id=e.revision_id,
            description=e.description,
        )


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


class ReviewSubmit(BaseModel):
    task_id: uuid.UUID
    reviewer_id: uuid.UUID | None = None
    note: str | None = None
    delay_reason: str | None = None
    #: Required when the hours drifted materially from the estimate, exactly as
    #: on the status endpoint. Without it here, a task that needs review and
    #: overran had no route forward at all: submitting is the only way into the
    #: review queue, and the transition it performs is one the variance rule
    #: guards.
    variance_reason: str | None = None
    variance_note: str | None = None


class ReviewDecision(BaseModel):
    result: str
    comments: str | None = None
    #: Required when the result is not an approval.
    revision_category: str | None = None
    revision_reason: str | None = None
    root_cause: str | None = None

    @field_validator("result")
    @classmethod
    def _known(cls, value: str) -> str:
        allowed = {r.value for r in ReviewResult}
        if value not in allowed:
            raise ValueError(f"result must be one of {', '.join(sorted(allowed))}")
        return value


class ReviewOut(ORMModel):
    id: uuid.UUID
    code: str
    task_id: uuid.UUID
    task_code: str | None = None
    task_name: str | None = None
    release_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    round_number: int
    status: str
    result: str | None = None
    submitted_by_id: uuid.UUID | None = None
    reviewer_id: uuid.UUID | None = None
    reviewer_name: str | None = None
    submitted_at: datetime
    review_started_at: datetime | None = None
    reviewed_at: datetime | None = None
    turnaround_hours: float | None = None
    comments: str | None = None

    @classmethod
    def from_model(cls, r) -> "ReviewOut":
        return cls(
            id=r.id,
            code=r.code,
            task_id=r.task_id,
            task_code=r.task.code if r.task else None,
            task_name=r.task.name if r.task else None,
            release_id=r.release_id,
            project_id=r.project_id,
            round_number=r.round_number,
            status=r.status,
            result=r.result,
            submitted_by_id=r.submitted_by_id,
            reviewer_id=r.reviewer_id,
            reviewer_name=r.reviewer.full_name if r.reviewer else None,
            submitted_at=r.submitted_at,
            review_started_at=r.review_started_at,
            reviewed_at=r.reviewed_at,
            turnaround_hours=(
                float(r.turnaround_hours) if r.turnaround_hours is not None else None
            ),
            comments=r.comments,
        )


# ---------------------------------------------------------------------------
# Revisions
# ---------------------------------------------------------------------------


class RevisionCreate(BaseModel):
    task_id: uuid.UUID
    category: str = Field(min_length=1, max_length=60)
    reason: str = Field(min_length=1)
    root_cause: str | None = None
    description: str | None = None
    assigned_to_id: uuid.UUID | None = None


class RevisionOut(ORMModel):
    id: uuid.UUID
    code: str
    task_id: uuid.UUID
    task_code: str | None = None
    task_name: str | None = None
    release_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    revision_number: int
    reason: str
    category: str
    accountability: str
    root_cause: str | None = None
    description: str | None = None
    raised_by_id: uuid.UUID | None = None
    assigned_to_id: uuid.UUID | None = None
    assigned_to_name: str | None = None
    raised_date: datetime
    resolved_date: datetime | None = None
    additional_hours: float
    status: str

    @classmethod
    def from_model(cls, r) -> "RevisionOut":
        return cls(
            id=r.id,
            code=r.code,
            task_id=r.task_id,
            task_code=r.task.code if r.task else None,
            task_name=r.task.name if r.task else None,
            release_id=r.release_id,
            project_id=r.project_id,
            revision_number=r.revision_number,
            reason=r.reason,
            category=r.category,
            accountability=r.accountability,
            root_cause=r.root_cause,
            description=r.description,
            raised_by_id=r.raised_by_id,
            assigned_to_id=r.assigned_to_id,
            assigned_to_name=r.assigned_to.full_name if r.assigned_to else None,
            raised_date=r.raised_date,
            resolved_date=r.resolved_date,
            additional_hours=float(r.additional_hours or 0),
            status=r.status,
        )


# ---------------------------------------------------------------------------
# Collaboration
# ---------------------------------------------------------------------------


class CommentCreate(BaseModel):
    entity_type: str = Field(min_length=1, max_length=40)
    entity_id: uuid.UUID
    body: str = Field(min_length=1)
    parent_comment_id: uuid.UUID | None = None
    mentions: list[uuid.UUID] = Field(default_factory=list)


class CommentOut(ORMModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    body: str
    author_id: uuid.UUID | None = None
    author_name: str | None = None
    parent_comment_id: uuid.UUID | None = None
    created_at: datetime


class AttachmentOut(ORMModel):
    id: uuid.UUID
    code: str
    entity_type: str
    entity_id: uuid.UUID
    file_name: str
    content_type: str | None = None
    size_bytes: int
    version: int
    is_current: bool
    storage_provider: str
    uploaded_by_id: uuid.UUID | None = None
    uploaded_by_name: str | None = None
    created_at: datetime


class NotificationOut(ORMModel):
    id: uuid.UUID
    event_type: str
    title: str
    body: str | None = None
    severity: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class MarkReadRequest(BaseModel):
    notification_ids: list[uuid.UUID] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Settings and audit
# ---------------------------------------------------------------------------


class SettingOut(ORMModel):
    id: uuid.UUID
    key: str
    category: str
    value: Any
    description: str | None = None
    is_system: bool
    updated_at: datetime


class SettingUpdate(BaseModel):
    value: Any


class AuditLogOut(ORMModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None = None
    entity_code: str | None = None
    action: str
    summary: str | None = None
    old_value: dict | None = None
    new_value: dict | None = None
    actor_id: uuid.UUID | None = None
    actor_email: str | None = None
    ip_address: str | None = None
    created_at: datetime


class StatusHistoryOut(ORMModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    from_status: str | None = None
    to_status: str
    duration_hours: float | None = None
    changed_by_id: uuid.UUID | None = None
    changed_at: datetime
    note: str | None = None
