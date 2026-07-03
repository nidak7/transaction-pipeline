from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus
from tests.api.conftest import RecordingDispatcher, create_completed_job


def test_upload_success(
    client: TestClient,
    dispatcher: RecordingDispatcher,
    sample_csv: bytes,
) -> None:
    response = client.post(
        "/jobs/upload",
        files={"file": ("transactions.csv", sample_csv, "text/csv")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "pending"
    assert [str(job_id) for job_id in dispatcher.dispatched] == [payload["job_id"]]


def test_upload_rejects_invalid_csv(client: TestClient) -> None:
    response = client.post(
        "/jobs/upload",
        files={"file": ("transactions.csv", b"not,a,valid,file\n1,2", "text/csv")},
    )

    assert response.status_code == 400
    assert "missing required columns" in response.json()["detail"]


def test_upload_rejects_empty_file(client: TestClient) -> None:
    response = client.post(
        "/jobs/upload",
        files={"file": ("transactions.csv", b"", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded CSV file is empty."


def test_missing_job_status_returns_404(client: TestClient) -> None:
    response = client.get(f"/jobs/{uuid4()}/status")

    assert response.status_code == 404


def test_status_endpoint_returns_pending_job(
    client: TestClient,
    db_session: Session,
) -> None:
    job = Job(
        filename="transactions.csv",
        storage_path="/tmp/transactions.csv",
        row_count_raw=2,
        status=JobStatus.PENDING,
    )
    db_session.add(job)
    db_session.commit()

    response = client.get(f"/jobs/{job.id}/status")

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["summary"] is None


def test_list_jobs_supports_status_filter(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            Job(
                filename="pending.csv",
                storage_path="/tmp/pending.csv",
                row_count_raw=1,
                status=JobStatus.PENDING,
            ),
            Job(
                filename="failed.csv",
                storage_path="/tmp/failed.csv",
                row_count_raw=1,
                status=JobStatus.FAILED,
            ),
        ],
    )
    db_session.commit()

    response = client.get("/jobs?status=failed&limit=10&offset=0")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["filename"] == "failed.csv"


def test_results_endpoint_returns_completed_job(
    client: TestClient,
    db_session: Session,
) -> None:
    job = create_completed_job(db_session)

    response = client.get(f"/jobs/{job.id}/results")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == str(job.id)
    assert len(payload["transactions"]) == 2
    assert len(payload["anomalies"]) == 1
    assert payload["summary"]["risk_level"] == "medium"
    assert payload["category_spend"][0]["category"] == "Food"


def test_results_endpoint_returns_conflict_until_completed(
    client: TestClient,
    db_session: Session,
) -> None:
    job = Job(
        filename="pending.csv",
        storage_path="/tmp/pending.csv",
        row_count_raw=1,
        status=JobStatus.PENDING,
    )
    db_session.add(job)
    db_session.commit()

    response = client.get(f"/jobs/{job.id}/results")

    assert response.status_code == 409
