from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.job import Job


json_type = JSON().with_variant(postgresql.JSONB, "postgresql")
bigint_pk_type = BigInteger().with_variant(Integer, "sqlite")


class JobSummary(Base):
    __tablename__ = "job_summaries"
    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name="ck_job_summaries_risk_level",
        ),
        Index("ix_job_summaries_job_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(
        bigint_pk_type,
        primary_key=True,
        autoincrement=True,
    )
    job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    total_spend_inr: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=0,
    )
    total_spend_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=0,
    )
    top_merchants: Mapped[list[dict[str, object]]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
    )
    anomaly_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)

    job: Mapped[Job] = relationship("Job", back_populates="summary")
