"""Find accounts that still use the seeded password, and shut them.

Seeding gives every account it creates the same password, which is right for a
laptop and wrong the moment the API is reachable from outside. The demo
department is fifteen fictional people, two of whom hold Design Manager and
Director permissions -- anyone who has read this repository knows how to sign
in as them.

Safe by default: reports and changes nothing. Pass --apply to deactivate.

Deactivating rather than deleting, because the demo project's releases, tasks
and time entries reference these people; removing them would blank out that
history. A deactivated account cannot sign in but stays readable as a name.

The administrator is never touched. Locking it would lock you out, and its
password is yours to change -- sign in and use Change password, or the
/api/auth/change-password endpoint.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.security import verify_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import Role, User  # noqa: E402

#: Passwords that seeding has used. A database seeded before the value was
#: changed still carries the old one, so both are checked.
SEEDED_PASSWORDS = ["Design@123", settings.SEED_DEFAULT_PASSWORD]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="deactivate the affected accounts; without it nothing changes",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        users = db.execute(select(User).order_by(User.email)).scalars().all()

        exposed: list[User] = []
        for user in users:
            if any(verify_password(pw, user.hashed_password) for pw in SEEDED_PASSWORDS):
                exposed.append(user)

        admin = [u for u in exposed if u.email == settings.ADMIN_EMAIL]
        others = [u for u in exposed if u.email != settings.ADMIN_EMAIL and u.is_active]

        print(f"Checked {len(users)} accounts.")
        print()

        if admin:
            print("!! The administrator still uses a seeded password:")
            for user in admin:
                print(f"     {user.email}")
            print("   Change it yourself after signing in. This script will not")
            print("   touch it, because locking it would lock you out.")
            print()

        if not others:
            print("No other account uses a seeded password. Nothing to do.")
            return 0

        role_names = dict(
            db.execute(select(Role.id, Role.name)).all()
        )

        print(f"Accounts that would be deactivated ({len(others)}):")
        for user in others:
            roles = (
                ", ".join(
                    role_names.get(link.role_id, "?") for link in user.roles
                )
                or "no role"
            )
            print(f"   {user.email:44} {user.full_name:26} {roles}")
        print()

        if not args.apply:
            print("Dry run. Nothing was changed. Re-run with --apply to deactivate.")
            return 0

        for user in others:
            user.is_active = False
        db.commit()
        print(f"Deactivated {len(others)} accounts. They can no longer sign in;")
        print("their names still appear on the work they are attached to.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
