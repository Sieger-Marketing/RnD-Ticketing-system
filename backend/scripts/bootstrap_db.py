"""Bring permissions, roles, default settings and the admin account up to date.

Migrations move the schema; this moves the rows the schema implies. They are
different problems and they drift apart quietly: adding a permission to a role
bundle, or a key to DEFAULT_SETTINGS, changes Python constants and nothing in
the database, so the new permission is never granted and the new setting never
appears on the settings screen. The code keeps working -- get_setting falls
back to the default -- which is exactly what makes it hard to notice.

That happened twice on 2026-08-26: a team lead's two new permissions and the
notifications.manager_copy_events setting both needed a hand-run to land.

Every step is additive and idempotent, so this is safe to run on every service
start and does nothing at all on the runs where nothing changed. It never
removes a permission, never overwrites a setting somebody edited, and never
resets an existing password.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.db.session import SessionLocal  # noqa: E402
from app.seed import bootstrap  # noqa: E402


def main() -> int:
    with SessionLocal() as db:
        result = bootstrap.run(db)
        db.commit()

    changed = {k: v for k, v in result.items() if v}
    if changed:
        print("bootstrap applied: " + ", ".join(f"{k}={v}" for k, v in changed.items()))
    else:
        print("bootstrap: nothing to apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
