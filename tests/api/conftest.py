from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db_session, get_job_dispatcher
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.main import create_app
from app.models.job import Job, JobStatus
from app.models.summary import JobSummary
from app.models.transaction import Transaction
from app.services.dispatcher import JobDispatcher


class RecordingDispatcher(JobDispatcher):
    def __init__(self) -> None:
        self.dispatched: list[UUID] = []

    def dispatch(self, job_id: UUID) -> None:
        self.dispatched.append(job_id)


@pytest.fixture
def dispatcher() -> RecordingDispatcher:
    return RecordingDispatcher()


@pytest.fixture
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(
    tmp_path: Path,
    session_factory: sessionmaker[Session],
    dispatcher: RecordingDispatcher,
) -> Generator[TestClient, None, None]:
    app = create_app()
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        upload_dir=tmp_path,
    )

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_job_dispatcher] = lambda: dispatcher
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session(
    session_factory: sessionmaker[Session],
) -> Generator[Session, None, None]:
    with session_factory() as session:
        yield session


@pytest.fixture
def sample_csv() -> bytes:
    return (
        b"txn_id,date,merchant,amount,currency,status,category,account_id,notes\n"
        b"TXN1,04-09-2024,Flipkart,10882.55,INR,SUCCESS,Shopping,ACC003,\n"
        b"TXN2,2024/02/05,Swiggy,$11325.79,INR,success,,ACC004,\n"
    )


def create_completed_job(session: Session) -> Job:
    job = Job(
        filename="transactions.csv",
        storage_path="/tmp/transactions.csv",
        status=JobStatus.COMPLETED,
        row_count_raw=2,
        row_count_clean=2,
        completed_at=datetime.now(tz=UTC),
    )
    session.add(job)
    session.flush()
    session.add_all(
        [
            Transaction(
                job_id=job.id,
                txn_id="TXN1",
                date=datetime(2024, 9, 4, tzinfo=UTC).date(),
                merchant="Flipkart",
                amount=Decimal("10882.55"),
                currency="INR",
                status="SUCCESS",
                category="Shopping",
                account_id="ACC003",
                is_anomaly=False,
                llm_failed=False,
            ),
            Transaction(
                job_id=job.id,
                txn_id="TXN2",
                date=datetime(2024, 2, 5, tzinfo=UTC).date(),
                merchant="Swiggy",
                amount=Decimal("11325.79"),
                currency="USD",
                status="SUCCESS",
                category="Food",
                account_id="ACC004",
                is_anomaly=True,
                anomaly_reason="USD used with domestic merchant",
                llm_category="Food",
                llm_raw_response='{"category":"Food"}',
                llm_failed=False,
            ),
        ],
    )
    session.add(
        JobSummary(
            job_id=job.id,
            total_spend_inr=Decimal("10882.55"),
            total_spend_usd=Decimal("11325.79"),
            top_merchants=[{"merchant": "Swiggy", "amount": 11325.79}],
            anomaly_count=1,
            narrative="Spending is concentrated across shopping and food.",
            risk_level="medium",
        ),
    )
    session.commit()
    return job
