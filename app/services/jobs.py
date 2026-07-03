from __future__ import annotations

import csv
import re
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from app.models.job import Job, JobStatus
from app.repositories.jobs import JobRepository
from app.schemas.jobs import (
    CategorySpend,
    JobResultsResponse,
    JobSummaryResponse,
    TransactionResponse,
)
from app.services.dispatcher import JobDispatcher, JobDispatchError
from app.utils.csv_contract import REQUIRED_COLUMNS, REQUIRED_NON_EMPTY_COLUMNS

SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class CsvValidationError(ValueError):
    pass


class JobNotFoundError(LookupError):
    pass


class JobResultsUnavailableError(RuntimeError):
    pass


class JobUploadService:
    def __init__(
        self,
        *,
        repository: JobRepository,
        dispatcher: JobDispatcher | None,
        upload_dir: Path,
    ) -> None:
        self._repository = repository
        self._dispatcher = dispatcher
        self._upload_dir = upload_dir

    async def create_from_upload(self, upload: UploadFile) -> Job:
        filename = _sanitize_filename(upload.filename)
        content = await upload.read()
        row_count = validate_csv_upload(filename=filename, content=content)

        storage_path: Path | None = None
        try:
            job = self._repository.create(
                filename=filename,
                storage_path="",
                row_count_raw=row_count,
            )
            storage_path = self._persist_upload(job.id, content)
            self._repository.update_storage_path(job, str(storage_path))
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            if storage_path is not None:
                storage_path.unlink(missing_ok=True)
            raise

        try:
            if self._dispatcher is None:
                raise JobDispatchError("No job dispatcher is configured.")
            self._dispatcher.dispatch(job.id)
        except JobDispatchError:
            job.status = JobStatus.FAILED
            job.error_message = "Unable to enqueue transaction processing job."
            self._repository.commit()
            raise

        return job

    def get_results(self, job_id: UUID) -> JobResultsResponse:
        job = self._repository.get(job_id)
        if job is None:
            raise JobNotFoundError("Job not found.")
        if job.status != JobStatus.COMPLETED:
            raise JobResultsUnavailableError("Job results are not available yet.")

        summary = self._repository.summary_for_job(job_id)
        if summary is None:
            raise JobResultsUnavailableError("Job summary is not available yet.")

        transactions = self._repository.transactions_for_job(job_id)
        anomalies = self._repository.anomalies_for_job(job_id)
        category_spend = [
            CategorySpend(category=category, currency=currency, total=total)
            for category, currency, total in self._repository.category_spend_for_job(
                job_id,
            )
        ]

        return JobResultsResponse(
            job_id=job.id,
            transactions=[
                TransactionResponse.model_validate(transaction)
                for transaction in transactions
            ],
            anomalies=[
                TransactionResponse.model_validate(transaction)
                for transaction in anomalies
            ],
            category_spend=category_spend,
            summary=JobSummaryResponse(
                total_spend_inr=summary.total_spend_inr,
                total_spend_usd=summary.total_spend_usd,
                top_merchants=summary.top_merchants,
                anomaly_count=summary.anomaly_count,
                narrative=summary.narrative,
                risk_level=summary.risk_level,
            ),
        )

    def _persist_upload(self, job_id: UUID, content: bytes) -> Path:
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        path = self._upload_dir / f"{job_id}.csv"
        path.write_bytes(content)
        return path


def validate_csv_upload(*, filename: str, content: bytes) -> int:
    if not filename.lower().endswith(".csv"):
        raise CsvValidationError("Only CSV uploads are supported.")
    if not content.strip():
        raise CsvValidationError("Uploaded CSV file is empty.")

    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvValidationError("Uploaded CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(decoded.splitlines())
    fieldnames = {field.strip() for field in reader.fieldnames or []}
    missing_columns = REQUIRED_COLUMNS - fieldnames
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise CsvValidationError(f"CSV is missing required columns: {missing}.")

    row_count = 0
    for row_number, row in enumerate(reader, start=2):
        if row.get(None) is not None:
            raise CsvValidationError(f"CSV row {row_number} has too many fields.")
        missing_values = [
            column
            for column in REQUIRED_NON_EMPTY_COLUMNS
            if row.get(column) is None or str(row[column]).strip() == ""
        ]
        if missing_values:
            missing = ", ".join(sorted(missing_values))
            raise CsvValidationError(
                f"CSV row {row_number} is missing required values: {missing}.",
            )
        row_count += 1

    if row_count == 0:
        raise CsvValidationError("Uploaded CSV must contain at least one transaction.")

    return row_count


def _sanitize_filename(filename: str | None) -> str:
    if filename is None or filename.strip() == "":
        raise CsvValidationError("Uploaded file must have a filename.")

    sanitized = SAFE_FILENAME_PATTERN.sub("_", Path(filename).name.strip())
    if sanitized in {"", ".", ".."}:
        raise CsvValidationError("Uploaded file must have a valid filename.")
    return sanitized
