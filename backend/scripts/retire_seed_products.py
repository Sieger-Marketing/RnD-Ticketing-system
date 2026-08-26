"""Retire the seeded product names the BOM import superseded.

The catalogue ended up holding two names for the same physical product: the
marketing names the demo seed created ("Tower Parking System", "Two-Post
Stacker") and the names the design team's own tracker uses, which the BOM
import created ("Tower", "Stacker"). Both were offered in the product dropdown,
which is what made choosing one feel like a coin toss.

The tracker names won because they carry every project and release in the
system, and because they are what the team actually says out loud. The seeded
ones carry nothing.

Retired, not deleted. `is_active = False` drops them out of the dropdown
immediately -- /api/products defaults to active_only -- while leaving the rows
in place, so this is one flag away from being undone and no history is lost if
something turns out to have pointed at them after all.

Guarded on purpose: a product is only retired when it has no projects and no
releases, AND every release standard hanging off it is byte-identical to one
already recorded against a product that is staying. Anything unique refuses to
be retired and is reported instead, because a standard that exists in only one
place is not a duplicate, it is the record.

Safe by default: prints what it would change. Pass --apply.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.models.catalog import Product  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.release import DesignRelease  # noqa: E402
from app.models.standard import ReleaseStandard  # noqa: E402

#: The names the demo seed introduced. Matched by name rather than by code so
#: the script says what it means and does not depend on insertion order.
SEEDED_NAMES = {
    "Tower Parking System",
    "Puzzle Parking System",
    "Automated Guided Vehicle Parking",
    "Two-Post Stacker",
    "Automated Storage & Retrieval System",
}

_IGNORED_COLUMNS = {"id", "product_id", "created_at", "updated_at"}


def _fingerprint(standard: ReleaseStandard) -> str:
    """What a standard says, independent of which product it hangs off."""
    fields = {
        column: getattr(standard, column)
        for column in standard.__table__.columns.keys()
        if column not in _IGNORED_COLUMNS
    }
    return repr(sorted((k, repr(v)) for k, v in fields.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()

    with SessionLocal() as db:
        products = db.execute(select(Product)).scalars().all()
        keeping = [p for p in products if p.name not in SEEDED_NAMES and p.is_active]

        # Every standard recorded against a product that is staying.
        surviving = {
            _fingerprint(s)
            for s in db.execute(
                select(ReleaseStandard).where(
                    ReleaseStandard.product_id.in_([p.id for p in keeping])
                )
            ).scalars()
        }

        project_counts = dict(
            db.execute(
                select(Project.product_id, func.count()).group_by(Project.product_id)
            ).all()
        )
        release_counts = dict(
            db.execute(
                select(DesignRelease.product_id, func.count()).group_by(
                    DesignRelease.product_id
                )
            ).all()
        )

        retired, refused = [], []

        for product in products:
            if product.name not in SEEDED_NAMES or not product.is_active:
                continue

            projects = project_counts.get(product.id, 0)
            releases = release_counts.get(product.id, 0)
            standards = db.execute(
                select(ReleaseStandard).where(ReleaseStandard.product_id == product.id)
            ).scalars().all()
            unique = [s for s in standards if _fingerprint(s) not in surviving]

            reasons = []
            if projects:
                reasons.append(f"{projects} project(s)")
            if releases:
                reasons.append(f"{releases} release(s)")
            if unique:
                reasons.append(f"{len(unique)} standard(s) recorded nowhere else")

            if reasons:
                refused.append((product, reasons))
                continue

            if args.apply:
                product.is_active = False
            retired.append((product, len(standards)))

        if args.apply:
            db.commit()

        print(f"Products: {len(products)}")
        for product, standards in retired:
            duplicate = f", {standards} duplicate standard(s)" if standards else ""
            print(f"  retire  {product.code}  {product.name}{duplicate}")
        for product, reasons in refused:
            print(f"  KEEP    {product.code}  {product.name} -- {', '.join(reasons)}")

        retired_ids = {p.id for p, _ in retired}
        remaining = sum(1 for p in products if p.is_active and p.id not in retired_ids)
        print()
        print(f"  retired : {len(retired)}")
        print(f"  refused : {len(refused)}")
        if args.apply:
            still_active = db.execute(
                select(func.count()).select_from(Product).where(Product.is_active.is_(True))
            ).scalar()
            print(f"  dropdown now offers: {still_active} product(s)")
        else:
            print(f"  dropdown would offer: {remaining} product(s)")
            print()
            print("Dry run. Nothing was changed. Re-run with --apply.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
