from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(name="transaction_pipeline.process_job")  # type: ignore[untyped-decorator]
def process_transaction_job(job_id: str) -> None:
    from app.services.pipeline import process_job

    process_job(UUID(job_id))
