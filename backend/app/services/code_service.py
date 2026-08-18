"""Allocation of human-readable entity codes (PRJ-0007, DR-0031, TSK-01042).

Spec section 3 requires every major entity to carry a readable identifier
alongside its UUID. Counters live in a table and are bumped under a row lock,
so two concurrent creates cannot receive the same code, and deleting a record
never causes its code to be handed out again.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.system import DocumentCounter

#: entity key -> (prefix, zero padding)
CODE_FORMATS: dict[str, tuple[str, int]] = {
    "user": ("EMP", 4),
    "customer": ("CUS", 4),
    "product": ("PRD", 4),
    "product_family": ("PF", 3),
    "project": ("PRJ", 4),
    "release": ("DR", 5),
    "task": ("TSK", 6),
    "template": ("TPL", 4),
    "time_entry": ("TE", 8),
    "review": ("REV", 6),
    "revision": ("RVN", 6),
    "attachment": ("FILE", 6),
}


def next_code(db: Session, entity: str) -> str:
    """Allocate the next code for `entity`.

    Uses SELECT ... FOR UPDATE so concurrent transactions serialise on the
    counter row instead of racing. The caller's transaction owns the lock
    until it commits.
    """
    prefix, padding = CODE_FORMATS.get(entity, (entity[:3].upper(), 5))

    counter = db.execute(
        select(DocumentCounter)
        .where(DocumentCounter.entity == entity)
        .with_for_update()
    ).scalar_one_or_none()

    if counter is None:
        counter = DocumentCounter(
            entity=entity, prefix=prefix, padding=padding, last_value=0
        )
        db.add(counter)
        db.flush()

    counter.last_value += 1
    db.flush()
    return f"{counter.prefix}-{counter.last_value:0{counter.padding}d}"


def peek_code(db: Session, entity: str) -> str:
    """The code that `next_code` would return, without consuming it."""
    prefix, padding = CODE_FORMATS.get(entity, (entity[:3].upper(), 5))
    counter = db.execute(
        select(DocumentCounter).where(DocumentCounter.entity == entity)
    ).scalar_one_or_none()
    nxt = (counter.last_value if counter else 0) + 1
    pad = counter.padding if counter else padding
    pfx = counter.prefix if counter else prefix
    return f"{pfx}-{nxt:0{pad}d}"
