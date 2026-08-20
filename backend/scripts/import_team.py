"""Create the design team's accounts from the roster.

People sign in with their employee code -- SIES00267 -- because that is the
identifier already on their card and on every drawing, and several of them
have no work mailbox. The email column still holds a value because it is the
system's unique key and predates this; where the roster gives no address, a
placeholder is derived from the code and should be replaced when the real one
is known.

Each account gets its own random initial password, written to a file for you
to hand out privately. One shared password would mean any of them could sign
in as any other, and the audit trail would be worth nothing.

Safe by default: prints what it would do and writes nothing. Pass --apply.

Re-running is safe. An account that already exists is updated -- name, role,
reporting line -- and its password is left alone, so this can be used to fix a
role without resetting anybody.

    python scripts/import_team.py                    # show the plan
    python scripts/import_team.py --apply            # create them
    python scripts/import_team.py --apply --reset-passwords
"""

from __future__ import annotations

import argparse
import json
import secrets
import string
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import Role, User, UserRole  # noqa: E402
from app.services import code_service  # noqa: E402

ROSTER = Path(__file__).resolve().parents[1] / "app" / "seed" / "data" / "design_team.json"

DEFAULT_ROLE = "Designer"
DEFAULT_DEPARTMENT = "Design"
EMAIL_DOMAIN = "sieger.in"

#: Unambiguous alphabet: no O/0, no l/1/I. These get read off a printout and
#: typed by hand, and a password nobody can transcribe is a support call.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def new_password(length: int = 12) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def placeholder_email(employee_code: str) -> str:
    return f"{employee_code.lower()}@{EMAIL_DOMAIN}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the accounts")
    parser.add_argument(
        "--reset-passwords",
        action="store_true",
        help="also give existing accounts a new password",
    )
    parser.add_argument(
        "--out",
        default="initial-passwords.csv",
        help="where to write the credentials for the accounts created",
    )
    args = parser.parse_args()

    roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    people = roster["people"]

    with SessionLocal() as db:
        roles = {r.name: r for r in db.execute(select(Role)).scalars()}
        missing_roles = {
            p.get("role", DEFAULT_ROLE) for p in people
        } - set(roles)
        if missing_roles:
            print(f"These roles do not exist: {', '.join(sorted(missing_roles))}")
            print(f"Available: {', '.join(sorted(roles))}")
            return 1

        created: list[tuple[str, str, str, str]] = []
        updated: list[str] = []

        for person in people:
            employee_code = person["employee_code"].strip().upper()
            full_name = person["full_name"].strip()
            role_name = person.get("role", DEFAULT_ROLE)
            email = person.get("email", placeholder_email(employee_code)).lower()

            user = db.execute(
                select(User).where(User.employee_code == employee_code)
            ).scalar_one_or_none()

            if user is None:
                # An account may predate the employee code, matched by email.
                user = db.execute(
                    select(User).where(User.email == email)
                ).scalar_one_or_none()

            if user is not None:
                updated.append(f"{employee_code}  {full_name}  ({role_name})")
                if not args.apply:
                    continue
                user.employee_code = employee_code
                user.full_name = full_name
                user.department = user.department or DEFAULT_DEPARTMENT
                if person.get("designation"):
                    user.designation = person["designation"]
                if args.reset_passwords:
                    password = new_password()
                    user.hashed_password = hash_password(password)
                    created.append((employee_code, full_name, email, password))
                for existing in list(user.roles):
                    db.delete(existing)
                db.flush()
                db.add(
                    UserRole(
                        user_id=user.id, role_id=roles[role_name].id, is_primary=True
                    )
                )
                continue

            password = new_password()
            created.append((employee_code, full_name, email, password))
            if not args.apply:
                continue

            user = User(
                code=code_service.next_code(db, "user"),
                email=email,
                employee_code=employee_code,
                hashed_password=hash_password(password),
                full_name=full_name,
                designation=person.get("designation"),
                department=DEFAULT_DEPARTMENT,
                standard_daily_hours=person.get("standard_daily_hours", 8),
                working_days_per_week=person.get("working_days_per_week", 6),
            )
            db.add(user)
            db.flush()
            db.add(
                UserRole(user_id=user.id, role_id=roles[role_name].id, is_primary=True)
            )

        db.flush()

        # Reporting lines in a second pass: a designer may be listed before the
        # lead they report to, and a one-pass import would silently drop the
        # link. Resolved by employee code so the roster stays readable.
        by_code = {
            u.employee_code: u
            for u in db.execute(
                select(User).where(User.employee_code.is_not(None))
            ).scalars()
        }
        lines = 0
        for person in people:
            target = person.get("reports_to")
            if not target:
                continue
            user = by_code.get(person["employee_code"].strip().upper())
            manager = by_code.get(target.strip().upper())
            if user is None or manager is None:
                print(f"  ! {person['employee_code']} -> {target}: one of them is missing")
                continue
            if args.apply and user.reports_to_id != manager.id:
                user.reports_to_id = manager.id
                lines += 1

        print(f"Roster: {len(people)} people")
        if lines:
            print(f"  reporting lines set: {lines}")
        print(f"  to create: {len(created) if not args.apply else len(created)}")
        print(f"  already present, would be updated: {len(updated)}")
        for line in updated:
            print(f"     {line}")
        print()

        if not args.apply:
            print("Dry run. Nothing was written. Re-run with --apply.")
            return 0

        db.commit()

        if created:
            out = Path(args.out).resolve()
            stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
            lines = [
                "# Initial passwords for the design team.",
                f"# Generated {stamp}. Hand these out privately, one per person.",
                "# Everyone should change theirs on first sign-in: the key icon",
                "# at the bottom of the sidebar. Delete this file afterwards.",
                "employee_code,name,email,initial_password",
            ]
            for employee_code, full_name, email, password in created:
                lines.append(f"{employee_code},{full_name},{email},{password}")
            out.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"Wrote {len(created)} credentials to {out}")
            print("That file is the only copy. Hand them out, then delete it.")
        else:
            print("No new accounts; no passwords written.")

        return 0


if __name__ == "__main__":
    raise SystemExit(main())
