"""add job storage path

Revision ID: 202607030002
Revises: 202607030001
Create Date: 2026-07-03 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "202607030002"
down_revision = "202607030001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "storage_path",
            sa.String(length=1024),
            server_default="",
            nullable=False,
        ),
    )
    op.alter_column("jobs", "storage_path", server_default=None)


def downgrade() -> None:
    op.drop_column("jobs", "storage_path")
