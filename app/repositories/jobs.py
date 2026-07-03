from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.job import Job, JobStatus
from app.models.summary import JobSummary
from app.models.transaction import Transaction
from app.services.cleaner import CleanedTransaction
from app.services.summarizer import SummaryResult


class JobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        filename: str,
        storage_path: str,
        row_count_raw: int,
    ) -> Job:
        job = Job(
            filename=filename,
            storage_path=storage_path,
            row_count_raw=row_count_raw,
        )
        self._session.add(job)
        self._session.flush()
        return job

    def update_storage_path(self, job: Job, storage_path: str) -> None:
        job.storage_path = storage_path
        self._session.flush()

    def mark_processing(self, job: Job) -> None:
        job.status = JobStatus.PROCESSING
        job.error_message = None
        self._session.flush()

    def mark_failed(self, job: Job, error_message: str) -> None:
        job.status = JobStatus.FAILED
        job.error_message = error_message[:4000]
        job.completed_at = datetime.now(tz=UTC)
        self._session.flush()

    def replace_results(
        self,
        *,
        job: Job,
        transactions: list[CleanedTransaction],
        summary: SummaryResult,
    ) -> None:
        self._session.execute(delete(Transaction).where(Transaction.job_id == job.id))
        self._session.execute(delete(JobSummary).where(JobSummary.job_id == job.id))
        self._session.add_all(
            [
                Transaction(
                    job_id=job.id,
                    txn_id=transaction.txn_id,
                    date=transaction.date,
                    merchant=transaction.merchant,
                    amount=transaction.amount,
                    currency=transaction.currency,
                    status=transaction.status,
                    category=transaction.category,
                    account_id=transaction.account_id,
                    is_anomaly=transaction.is_anomaly,
                    anomaly_reason=transaction.anomaly_reason,
                    llm_category=transaction.llm_category,
                    llm_raw_response=transaction.llm_raw_response,
                    llm_failed=transaction.llm_failed,
                )
                for transaction in transactions
            ],
        )
        self._session.add(
            JobSummary(
                job_id=job.id,
                total_spend_inr=summary.total_spend_inr,
                total_spend_usd=summary.total_spend_usd,
                top_merchants=summary.top_merchants,
                anomaly_count=summary.anomaly_count,
                narrative=summary.narrative,
                risk_level=summary.risk_level,
            ),
        )
        job.status = JobStatus.COMPLETED
        job.row_count_clean = len(transactions)
        job.completed_at = datetime.now(tz=UTC)
        job.error_message = None
        self._session.flush()

    def get(self, job_id: UUID) -> Job | None:
        return self._session.get(Job, job_id)

    def get_with_summary(self, job_id: UUID) -> Job | None:
        statement = (
            select(Job).where(Job.id == job_id).options(selectinload(Job.summary))
        )
        return self._session.scalar(statement)

    def list(
        self,
        *,
        status: JobStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[Job]:
        statement = self._job_list_statement(status).limit(limit).offset(offset)
        return self._session.scalars(statement).all()

    def count(self, *, status: JobStatus | None) -> int:
        statement = select(func.count()).select_from(Job)
        if status is not None:
            statement = statement.where(Job.status == status)
        return self._session.scalar(statement) or 0

    def transactions_for_job(self, job_id: UUID) -> Sequence[Transaction]:
        statement = (
            select(Transaction)
            .where(Transaction.job_id == job_id)
            .order_by(Transaction.date, Transaction.id)
        )
        return self._session.scalars(statement).all()

    def summary_for_job(self, job_id: UUID) -> JobSummary | None:
        statement = select(JobSummary).where(JobSummary.job_id == job_id)
        return self._session.scalar(statement)

    def anomalies_for_job(self, job_id: UUID) -> Sequence[Transaction]:
        statement = (
            select(Transaction)
            .where(Transaction.job_id == job_id, Transaction.is_anomaly.is_(True))
            .order_by(Transaction.date, Transaction.id)
        )
        return self._session.scalars(statement).all()

    def category_spend_for_job(
        self, job_id: UUID
    ) -> Sequence[tuple[str, str, Decimal]]:
        statement = (
            select(
                Transaction.category,
                Transaction.currency,
                func.sum(Transaction.amount),
            )
            .where(Transaction.job_id == job_id)
            .group_by(Transaction.category, Transaction.currency)
            .order_by(Transaction.category, Transaction.currency)
        )
        return [
            (row[0], row[1], cast(Decimal, row[2]))
            for row in self._session.execute(statement).all()
        ]

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    @staticmethod
    def _job_list_statement(status: JobStatus | None) -> Select[tuple[Job]]:
        statement = select(Job).order_by(Job.created_at.desc())
        if status is not None:
            statement = statement.where(Job.status == status)
        return statement
