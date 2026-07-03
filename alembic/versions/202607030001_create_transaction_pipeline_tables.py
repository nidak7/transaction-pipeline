"""create transaction pipeline tables

Revision ID: 202607030001
Revises:
Create Date: 2026-07-03 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "202607030001"
down_revision = None
branch_labels = None
depends_on = None


job_status = postgresql.ENUM(
    "pending",
    "processing",
    "completed",
    "failed",
    name="job_status",
)


def upgrade() -> None:
    job_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            job_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("row_count_raw", sa.Integer(), nullable=True),
        sa.Column("row_count_clean", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_status_created_at", "jobs", ["status", "created_at"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("txn_id", sa.String(length=128), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("merchant", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column(
            "is_anomaly",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("anomaly_reason", sa.Text(), nullable=True),
        sa.Column("llm_category", sa.String(length=64), nullable=True),
        sa.Column("llm_raw_response", sa.Text(), nullable=True),
        sa.Column(
            "llm_failed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_job_id", "transactions", ["job_id"])
    op.create_index("ix_transactions_txn_id", "transactions", ["txn_id"])
    op.create_index(
        "ix_transactions_job_anomaly",
        "transactions",
        ["job_id", "is_anomaly"],
    )
    op.create_index(
        "ix_transactions_job_category",
        "transactions",
        ["job_id", "category"],
    )

    op.create_table(
        "job_summaries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "total_spend_inr",
            sa.Numeric(precision=14, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "total_spend_usd",
            sa.Numeric(precision=14, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "top_merchants",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("anomaly_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name="ck_job_summaries_risk_level",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_job_summaries_job_id", "job_summaries", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_summaries_job_id", table_name="job_summaries")
    op.drop_table("job_summaries")

    op.drop_index("ix_transactions_job_category", table_name="transactions")
    op.drop_index("ix_transactions_job_anomaly", table_name="transactions")
    op.drop_index("ix_transactions_txn_id", table_name="transactions")
    op.drop_index("ix_transactions_job_id", table_name="transactions")
    op.drop_table("transactions")

    op.drop_index("ix_jobs_status_created_at", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")

    job_status.drop(op.get_bind(), checkfirst=True)
