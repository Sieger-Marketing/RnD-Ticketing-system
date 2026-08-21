"""Workflow vocabularies, readable by anyone who is signed in.

Why this exists as its own module rather than living under /settings:

The configured vocabularies serve two different audiences. Editing them is
administration and belongs behind ``settings.manage``. *Reading* them is not:
the API requires a designer to supply a delay reason, a team lead to supply a
task type, and a release to name a release type -- and every one of those
values must come from the configured list. Gating the list behind
``settings.view``, which only the Design Manager holds, leaves those roles
unable to complete a form the API insists they fill in. That exact mismatch has
produced a run of user-facing dead ends, so the reachable half is collected
here once instead of being rediscovered per screen.

It also sits on its own prefix deliberately. ``/api/revisions/categories``
resolves today only because no ``/api/revisions/{revision_id}`` route exists
yet; adding one would shadow it and turn the vocabulary fetch into a 422 on the
literal string "categories". A prefix with no path parameters cannot develop
that problem.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import settings_service

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/vocabularies")
def vocabularies(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    """Every configured list a form needs, plus the rules that govern them.

    ``require_delay_reason`` is included because without it a client cannot
    tell whether the delay reason is mandatory, and designers end up
    discovering the rule through a rejected submit.
    """
    return {
        "hold_reasons": settings_service.get_setting(db, "workflow.hold_reasons"),
        "variance_reasons": settings_service.get_setting(
            db, "workflow.variance_reasons"
        ),
        "variance_threshold_percent": settings_service.get_setting(
            db, "workflow.variance_threshold_percent", 25
        ),
        "delay_reasons": settings_service.get_setting(db, "workflow.delay_reasons"),
        "revision_categories": settings_service.get_setting(
            db, "workflow.revision_categories"
        ),
        "task_types": settings_service.get_setting(db, "workflow.task_types"),
        "release_types": settings_service.get_setting(db, "workflow.release_types"),
        "project_types": settings_service.get_setting(db, "workflow.project_types"),
        "require_delay_reason": settings_service.get_setting(
            db, "workflow.require_delay_reason", True
        ),
        # The band legend, so a designer's own utilisation badge can explain
        # itself rather than showing a colour with no scale behind it.
        "capacity_thresholds": settings_service.get_setting(db, "capacity.thresholds"),
    }
