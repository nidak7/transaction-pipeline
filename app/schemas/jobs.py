from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import Job, JobStatus


class JobUploadResponse(BaseModel):
    job_id: UUID
    status: JobStatus


class JobListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    status: JobStatus
    row_count_raw: int | None
    row_count_clean: int | None
    created_at: datetime


class JobListResponse(BaseModel):
    items: list[JobListItem]
    total: int
    limit: int
    offset: int


class JobStatusSummary(BaseModel):
    total_spend_inr: Decimal
    total_spend_usd: Decimal
    anomaly_count: int
    risk_level: str


class JobStatusResponse(BaseModel):
    id: UUID
    filename: str
    status: JobStatus
    row_count_raw: int | None
    row_count_clean: int | None
    created_at: datetime
    completed_at: datetime | None
    error_message: str | None
    summary: JobStatusSummary | None

    @classmethod
    def from_job(cls, job: Job) -> JobStatusResponse:
        summary = None
        if job.summary is not None:
            summary = JobStatusSummary(
                total_spend_inr=job.summary.total_spend_inr,
                total_spend_usd=job.summary.total_spend_usd,
                anomaly_count=job.summary.anomaly_count,
                risk_level=job.summary.risk_level,
            )

        return cls(
            id=job.id,
            filename=job.filename,
            status=job.status,
            row_count_raw=job.row_count_raw,
            row_count_clean=job.row_count_clean,
            created_at=job.created_at,
            completed_at=job.completed_at,
            error_message=job.error_message,
            summary=summary,
        )


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    txn_id: str
    date: date
    merchant: str
    amount: Decimal
    currency: str
    status: str
    category: str
    account_id: str
    is_anomaly: bool
    anomaly_reason: str | None
    llm_category: str | None
    llm_raw_response: str | None
    llm_failed: bool


class CategorySpend(BaseModel):
    category: str
    currency: str
    total: Decimal


class JobSummaryResponse(BaseModel):
    total_spend_inr: Decimal
    total_spend_usd: Decimal
    top_merchants: list[dict[str, Any]] = Field(default_factory=list)
    anomaly_count: int
    narrative: str
    risk_level: str


class JobResultsResponse(BaseModel):
    job_id: UUID
    transactions: list[TransactionResponse]
    anomalies: list[TransactionResponse]
    category_spend: list[CategorySpend]
    summary: JobSummaryResponse
