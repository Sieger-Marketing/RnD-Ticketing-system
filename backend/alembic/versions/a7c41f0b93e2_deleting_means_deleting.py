"""Deleting means deleting: release.delete, and Team Leads lose project.delete

DELETE on a project, release or task used to set status to Cancelled. It now
removes the rows. Two grant changes follow from that, and neither can be left
to the bootstrap, which is additive by design and never revokes anything:

* `release.delete` is new. The endpoint was gated on `release.update`, which
  conflated editing a release with destroying every hour logged against it.
  Granted to Administrator and Design Manager.

* Team Lead loses `project.delete`. It was granted on the stated basis that
  deleting was a soft cancel and the history survived. That is no longer true,
  so the grant goes. Team Leads keep `task.delete` and can still cancel a
  project or a release through the status endpoints.

Runtime grants an administrator added by hand are left alone -- this touches
only the two role/permission pairs named above.

Revision ID: a7c41f0b93e2
Revises: 5fbda7a9cc87
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7c41f0b93e2"
down_revision = "5fbda7a9cc87"
branch_labels = None
depends_on = None


NEW_PERMISSION = (
    "release.delete",
    "releases",
    "Permanently delete a release, with its tasks and logged time",
)
GRANT_TO = ("Administrator", "Design Manager")
REVOKE_PROJECT_DELETE_FROM = "Team Lead"


def upgrade() -> None:
    conn = op.get_bind()

    code, module, description = NEW_PERMISSION

    # gen_random_uuid() is pgcrypto, in core since PG 13; this schema is on 16+.
    conn.execute(
        sa.text(
            """
            INSERT INTO permissions (id, code, module, description,
                                     created_at, updated_at)
            VALUES (gen_random_uuid(), :code, :module, :description, now(), now())
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {"code": code, "module": module, "description": description},
    )

    for role_name in GRANT_TO:
        conn.execute(
            sa.text(
                """
                INSERT INTO role_permissions (id, role_id, permission_id)
                SELECT gen_random_uuid(), r.id, p.id
                FROM roles r, permissions p
                WHERE r.name = :role AND p.code = :code
                  AND NOT EXISTS (
                      SELECT 1 FROM role_permissions rp
                      WHERE rp.role_id = r.id AND rp.permission_id = p.id
                  )
                """
            ),
            {"role": role_name, "code": code},
        )

    conn.execute(
        sa.text(
            """
            DELETE FROM role_permissions rp
            USING roles r, permissions p
            WHERE rp.role_id = r.id AND rp.permission_id = p.id
              AND r.name = :role AND p.code = 'project.delete'
            """
        ),
        {"role": REVOKE_PROJECT_DELETE_FROM},
    )

    # The two descriptions that now promise something different.
    for permission_code, text in (
        (
            "project.delete",
            "Permanently delete a project, with its releases, tasks and logged time",
        ),
        (
            "task.delete",
            "Permanently delete a task, with its time entries, reviews and revisions",
        ),
    ):
        conn.execute(
            sa.text(
                "UPDATE permissions SET description = :text, updated_at = now() "
                "WHERE code = :code"
            ),
            {"text": text, "code": permission_code},
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Give the Team Lead back project.delete.
    conn.execute(
        sa.text(
            """
            INSERT INTO role_permissions (id, role_id, permission_id)
            SELECT gen_random_uuid(), r.id, p.id
            FROM roles r, permissions p
            WHERE r.name = :role AND p.code = 'project.delete'
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        ),
        {"role": REVOKE_PROJECT_DELETE_FROM},
    )

    # Drop release.delete and every grant of it.
    conn.execute(
        sa.text(
            """
            DELETE FROM role_permissions rp
            USING permissions p
            WHERE rp.permission_id = p.id AND p.code = 'release.delete'
            """
        )
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'release.delete'"))

    for permission_code, text in (
        ("project.delete", "Delete or cancel a project"),
        ("task.delete", "Remove a task"),
    ):
        conn.execute(
            sa.text(
                "UPDATE permissions SET description = :text, updated_at = now() "
                "WHERE code = :code"
            ),
            {"text": text, "code": permission_code},
        )
