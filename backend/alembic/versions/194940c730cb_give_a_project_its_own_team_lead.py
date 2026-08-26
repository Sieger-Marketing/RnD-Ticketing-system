"""Give a project its own team lead

A release and a task each already carry a team_lead_id; a project did not. So a
lead could only be attached to a project indirectly -- by walking down to a
release they happened to lead -- which returns nothing for a project whose
releases have not been created yet. That is exactly the moment somebody needs
to own it.

Nullable on purpose. The existing projects have no lead recorded anywhere to
backfill from, and inventing one would be worse than leaving it blank: an empty
field reads as "nobody has been assigned", a wrong one reads as settled.

Revision ID: 194940c730cb
Revises: 6b70f437c3d1
Create Date: 2026-08-26 16:37:35.433281
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '194940c730cb'
down_revision: str | None = '6b70f437c3d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "fk_projects_team_lead_id_users"


def upgrade() -> None:
    op.add_column('projects', sa.Column('team_lead_id', sa.UUID(), nullable=True))
    op.create_index(
        op.f('ix_projects_team_lead_id'), 'projects', ['team_lead_id'], unique=False
    )
    # Mirrors ix_projects_manager_status: a lead's own project list filters on
    # lead plus status, and that is the query the leads themselves will run.
    op.create_index(
        'ix_projects_lead_status', 'projects', ['team_lead_id', 'status'], unique=False
    )
    # Named on purpose, so the downgrade can drop it. Autogenerate emitted
    # drop_constraint(None, ...), which fails at runtime.
    op.create_foreign_key(
        FK_NAME, 'projects', 'users', ['team_lead_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, 'projects', type_='foreignkey')
    op.drop_index('ix_projects_lead_status', table_name='projects')
    op.drop_index(op.f('ix_projects_team_lead_id'), table_name='projects')
    op.drop_column('projects', 'team_lead_id')
