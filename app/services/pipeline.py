from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.llm.base import LLMClient
from app.llm.factory import create_llm_client
from app.models.job import Job
from app.repositories.jobs import JobRepository
from app.services.anomaly import detect_anomalies
from app.services.classifier import RetryPolicy, classify_uncategorized_transactions
from app.services.cleaner import clean_csv
from app.services.summarizer import generate_summary

logger = logging.getLogger(__name__)


class PipelineExecutionError(RuntimeError):
    pass


def process_job(
    job_id: UUID,
    *,
    session_factory: sessionmaker[Session] | None = None,
    client_factory: Callable[[Settings], LLMClient] = create_llm_client,
    settings: Settings | None = None,
) -> None:
    active_settings = settings or get_settings()
    factory = session_factory or get_session_factory()

    with factory() as session:
        repository = JobRepository(session)
        job = repository.get(job_id)
        if job is None:
            logger.error(
                "Job not found.",
                extra={"job_id": str(job_id), "stage": "load_job"},
            )
            return

        try:
            repository.mark_processing(job)
            repository.commit()
            _run_pipeline(
                repository,
                job,
                client_factory(active_settings),
                active_settings,
            )
            repository.commit()
        except Exception as exc:
            repository.rollback()
            job = repository.get(job_id)
            if job is not None:
                repository.mark_failed(job, str(exc))
                repository.commit()
            logger.error(
                "Pipeline failed.",
                extra={"job_id": str(job_id), "stage": "pipeline"},
                exc_info=True,
            )
            raise


def _run_pipeline(
    repository: JobRepository,
    job: Job,
    client: LLMClient,
    settings: Settings,
) -> None:
    retry_policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=settings.llm_retry_base_delay_seconds,
    )
    with _stage(job.id, "cleaning"):
        cleaning_result = clean_csv(Path(job.storage_path))

    with _stage(job.id, "anomaly_detection"):
        transactions = detect_anomalies(cleaning_result.transactions)

    with _stage(job.id, "llm_classification"):
        classify_uncategorized_transactions(
            transactions,
            client=client,
            batch_size=settings.llm_batch_size,
            retry_policy=retry_policy,
            job_id=str(job.id),
        )

    with _stage(job.id, "llm_summary"):
        summary = generate_summary(
            transactions,
            client=client,
            retry_policy=retry_policy,
            job_id=str(job.id),
        )

    with _stage(job.id, "persist_results"):
        job.row_count_raw = cleaning_result.row_count_raw
        repository.replace_results(
            job=job,
            transactions=transactions,
            summary=summary,
        )


@contextmanager
def _stage(job_id: UUID, stage: str) -> Iterator[None]:
    started = perf_counter()
    try:
        yield
    except Exception:
        duration_ms = round((perf_counter() - started) * 1000, 2)
        logger.error(
            "Pipeline stage failed.",
            extra={
                "job_id": str(job_id),
                "stage": stage,
                "duration_ms": duration_ms,
            },
            exc_info=True,
        )
        raise
    else:
        duration_ms = round((perf_counter() - started) * 1000, 2)
        logger.info(
            "Pipeline stage completed.",
            extra={
                "job_id": str(job_id),
                "stage": stage,
                "duration_ms": duration_ms,
            },
        )
