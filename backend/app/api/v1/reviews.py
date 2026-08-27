"""Review and revision endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import (
    AccessScope,
    client_context,
    get_current_user,
    get_scope,
    require_permission,
)
from app.core.enums import ReviewStatus, RevisionStatus
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import P
from app.db.session import get_db
from app.models.execution import Review, Revision
from app.models.task import Task
from app.models.user import User
from app.schemas.common import Page
from app.schemas.execution import (
    ReviewDecision,
    ReviewOut,
    ReviewSubmit,
    RevisionCreate,
    RevisionOut,
)
from app.services import review_service, settings_service

router = APIRouter(tags=["reviews"])


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


@router.get("/reviews", response_model=Page[ReviewOut])
def list_reviews(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    reviewer_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    release_id: uuid.UUID | None = None,
    status: list[str] | None = Query(None),
    pending_only: bool = False,
) -> Page[ReviewOut]:
    stmt = select(Review)

    # Without the all-reviews permission a user sees only what they submitted
    # or what is waiting on them.
    if P.REVIEW_VIEW_ALL not in scope.permissions:
        stmt = stmt.where(
            or_(Review.reviewer_id == scope.user.id, Review.submitted_by_id == scope.user.id)
        )
    if reviewer_id:
        stmt = stmt.where(Review.reviewer_id == reviewer_id)
    if task_id:
        stmt = stmt.where(Review.task_id == task_id)
    if project_id:
        stmt = stmt.where(Review.project_id == project_id)
    if release_id:
        stmt = stmt.where(Review.release_id == release_id)
    if status:
        stmt = stmt.where(Review.status.in_(status))
    if pending_only:
        stmt = stmt.where(
            Review.status.in_([ReviewStatus.PENDING.value, ReviewStatus.IN_REVIEW.value])
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = (
        db.execute(
            stmt.order_by(Review.submitted_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return Page.build([ReviewOut.from_model(r) for r in rows], total, page, page_size)


@router.get("/reviews/queue", response_model=list[ReviewOut])
def my_review_queue(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.REVIEW_PERFORM)),
) -> list[ReviewOut]:
    """What is waiting on me, oldest submission first."""
    rows = (
        db.execute(
            select(Review)
            .where(
                Review.reviewer_id == user.id,
                Review.status.in_(
                    [ReviewStatus.PENDING.value, ReviewStatus.IN_REVIEW.value]
                ),
            )
            .order_by(Review.submitted_at.asc())
        )
        .scalars()
        .all()
    )
    return [ReviewOut.from_model(r) for r in rows]


@router.post("/reviews/submit", response_model=ReviewOut, status_code=201)
def submit_for_review(
    payload: ReviewSubmit,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReviewOut:
    task = db.get(Task, payload.task_id)
    if task is None:
        raise NotFoundError("Task not found.")
    if task.assigned_to_id != user.id and P.TASK_UPDATE not in user.permission_codes:
        raise PermissionDeniedError("You can only submit your own tasks for review.")

    review = review_service.submit_for_review(
        db,
        task=task,
        actor=user,
        reviewer_id=payload.reviewer_id,
        note=payload.note,
        delay_reason=payload.delay_reason,
        variance_reason=payload.variance_reason,
        variance_note=payload.variance_note,
        context=client_context(request),
    )
    return ReviewOut.from_model(review)


@router.post("/reviews/{review_id}/start", response_model=ReviewOut)
def start_review(
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.REVIEW_PERFORM)),
) -> ReviewOut:
    review = db.get(Review, review_id)
    if review is None:
        raise NotFoundError("Review not found.")
    review_service.start_review(db, review=review, actor=user)
    return ReviewOut.from_model(review)


@router.post("/reviews/{review_id}/decision", response_model=dict)
def decide_review(
    review_id: uuid.UUID,
    payload: ReviewDecision,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.REVIEW_PERFORM)),
) -> dict:
    """Approve, reject or request a revision."""
    review = db.get(Review, review_id)
    if review is None:
        raise NotFoundError("Review not found.")

    review, revision = review_service.complete_review(
        db,
        review=review,
        actor=user,
        result=payload.result,
        comments=payload.comments,
        revision_category=payload.revision_category,
        revision_reason=payload.revision_reason,
        root_cause=payload.root_cause,
        context=client_context(request),
    )
    return {
        "review": ReviewOut.from_model(review).model_dump(mode="json"),
        "revision": (
            RevisionOut.from_model(revision).model_dump(mode="json")
            if revision
            else None
        ),
    }


@router.get("/reviews/first-pass")
def first_pass(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.REVIEW_VIEW_ALL)),
    project_id: uuid.UUID | None = None,
    assigned_to_id: uuid.UUID | None = None,
) -> dict:
    """First-Pass Approval %, optionally scoped to a project or a designer."""
    task_ids = None
    if project_id or assigned_to_id:
        stmt = select(Task.id)
        if project_id:
            stmt = stmt.where(Task.project_id == project_id)
        if assigned_to_id:
            stmt = stmt.where(Task.assigned_to_id == assigned_to_id)
        task_ids = [row[0] for row in db.execute(stmt).all()]
    return review_service.first_pass_stats(db, task_ids=task_ids)


# ---------------------------------------------------------------------------
# Revisions
# ---------------------------------------------------------------------------


@router.get("/revisions", response_model=Page[RevisionOut])
def list_revisions(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    task_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    release_id: uuid.UUID | None = None,
    assigned_to_id: uuid.UUID | None = None,
    category: list[str] | None = Query(None),
    accountability: str | None = None,
    status: list[str] | None = Query(None),
    open_only: bool = False,
) -> Page[RevisionOut]:
    stmt = select(Revision)

    if P.REVISION_VIEW_ALL not in scope.permissions:
        stmt = stmt.where(
            or_(
                Revision.assigned_to_id == scope.user.id,
                Revision.raised_by_id == scope.user.id,
            )
        )
    if task_id:
        stmt = stmt.where(Revision.task_id == task_id)
    if project_id:
        stmt = stmt.where(Revision.project_id == project_id)
    if release_id:
        stmt = stmt.where(Revision.release_id == release_id)
    if assigned_to_id:
        scope.assert_can_view_user(assigned_to_id)
        stmt = stmt.where(Revision.assigned_to_id == assigned_to_id)
    if category:
        stmt = stmt.where(Revision.category.in_(category))
    if accountability:
        stmt = stmt.where(Revision.accountability == accountability)
    if status:
        stmt = stmt.where(Revision.status.in_(status))
    if open_only:
        stmt = stmt.where(
            Revision.status.in_(
                [RevisionStatus.OPEN.value, RevisionStatus.IN_PROGRESS.value]
            )
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = (
        db.execute(
            stmt.order_by(Revision.raised_date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return Page.build([RevisionOut.from_model(r) for r in rows], total, page, page_size)


@router.post("/revisions", response_model=RevisionOut, status_code=201)
def create_revision(
    payload: RevisionCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.REVISION_CREATE)),
) -> RevisionOut:
    task = db.get(Task, payload.task_id)
    if task is None:
        raise NotFoundError("Task not found.")
    revision = review_service.create_revision(
        db,
        task=task,
        actor=user,
        category=payload.category,
        reason=payload.reason,
        root_cause=payload.root_cause,
        description=payload.description,
        assigned_to_id=payload.assigned_to_id,
        context=client_context(request),
    )
    return RevisionOut.from_model(revision)


@router.post("/revisions/{revision_id}/resolve", response_model=RevisionOut)
def resolve_revision(
    revision_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.REVISION_RESOLVE)),
) -> RevisionOut:
    revision = db.get(Revision, revision_id)
    if revision is None:
        raise NotFoundError("Revision not found.")
    review_service.resolve_revision(
        db, revision=revision, actor=user, context=client_context(request)
    )
    return RevisionOut.from_model(revision)


@router.get("/revisions/categories")
def revision_categories(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict]:
    """Configured categories and whether each counts as controllable rework."""
    return settings_service.get_setting(db, "workflow.revision_categories")
