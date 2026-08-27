"""A Team Lead can start a project

The lead is usually the first person to hear about a job, and having to wait
for a Design Manager to type it in was the step where work quietly got done
before it existed in the system.

Only project.create. It does not widen what they can see: visible_projects
matches on created_by_id among other things, so a lead sees the projects they
started without being handed the department. And it is not project.delete,
which stays with the Administrator and the Design Manager.

Revision ID: c3e8a5d17b40
Revises: a7c41f0b93e2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3e8a5d17b40"
down_revision = "a7c41f0b93e2"
branch_labels = None
depends_on = None

ROLE = "Team Lead"
CODE = "project.create"


def upgrade() -> None:
    op.get_bind().execute(
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
        {"role": ROLE, "code": CODE},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM role_permissions rp
            USING roles r, permissions p
            WHERE rp.role_id = r.id AND rp.permission_id = p.id
              AND r.name = :role AND p.code = :code
            """
        ),
        {"role": ROLE, "code": CODE},
    )
