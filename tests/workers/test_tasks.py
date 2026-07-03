from uuid import uuid4

from app.workers.tasks import process_transaction_job


def test_celery_task_delegates_to_pipeline(monkeypatch) -> None:
    seen: list[str] = []
    job_id = uuid4()

    def fake_process_job(value) -> None:
        seen.append(str(value))

    monkeypatch.setattr("app.services.pipeline.process_job", fake_process_job)

    process_transaction_job(str(job_id))

    assert seen == [str(job_id)]
