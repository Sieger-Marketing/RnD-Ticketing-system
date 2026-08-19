"""Report generation and export (spec section 28).

One endpoint per report, one `format` parameter. JSON renders the report on
screen; csv, xlsx and pdf return the same content as a download, so what a
manager sees is what they send on.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.errors import ValidationError
from app.core.permissions import P
from app.db.session import get_db
from app.models.user import User
from app.services import export_service, report_service

router = APIRouter(prefix="/reports", tags=["reports"])

_FORMATS = ("json", "csv", "xlsx", "pdf")


@router.get("")
def catalogue(
    _: User = Depends(require_permission(P.REPORT_EXPORT)),
) -> dict:
    """What can be generated, and what each one takes.

    Lets the reports screen build itself from the server rather than
    hard-coding a list that drifts the moment a report is added.
    """
    return {
        "formats": list(_FORMATS),
        "reports": [
            {
                "key": "daily",
                "title": "Daily Design Report",
                "description": (
                    "What completed today, what is overdue, what is blocked, "
                    "and which reviews are waiting."
                ),
                "parameter": "on",
                "parameter_label": "Date",
            },
            {
                "key": "weekly",
                "title": "Weekly Design Report",
                "description": (
                    "Productivity per designer, planned against actual hours, "
                    "releases completed and rework raised."
                ),
                "parameter": "week_of",
                "parameter_label": "Any date in the week",
            },
            {
                "key": "monthly",
                "title": "Monthly Management Report",
                "description": (
                    "Department efficiency, team lead and designer performance, "
                    "project delivery, capacity and the six-month trend."
                ),
                "parameter": "month_of",
                "parameter_label": "Any date in the month",
            },
        ],
    }


def _respond(report, fmt: str) -> Response | dict:
    if fmt == "json":
        return export_service.to_dict(report)

    renderer = export_service.RENDERERS.get(fmt)
    if renderer is None:
        raise ValidationError(
            f"Unknown format '{fmt}'.", details={"allowed": list(_FORMATS)}
        )

    render, media_type, extension = renderer
    payload = render(report)
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{report.filename_stem}.{extension}"'
            ),
            # The browser needs this exposed or a fetch-based download cannot
            # read the filename the server chose.
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/daily")
def daily(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.REPORT_EXPORT)),
    on: date | None = None,
    format: str = Query("json", pattern="^(json|csv|xlsx|pdf)$"),
):
    report = report_service.daily_report(db, on=on, actor=user)
    return _respond(report, format)


@router.get("/weekly")
def weekly(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.REPORT_EXPORT)),
    week_of: date | None = None,
    format: str = Query("json", pattern="^(json|csv|xlsx|pdf)$"),
):
    report = report_service.weekly_report(db, week_of=week_of, actor=user)
    return _respond(report, format)


@router.get("/monthly")
def monthly(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.REPORT_EXPORT)),
    month_of: date | None = None,
    format: str = Query("json", pattern="^(json|csv|xlsx|pdf)$"),
):
    report = report_service.monthly_report(db, month_of=month_of, actor=user)
    return _respond(report, format)
