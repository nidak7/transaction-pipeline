from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.llm.base import LLMClient
from app.models import Job, JobStatus, Transaction
from app.services.pipeline import process_job


class PipelineLLM(LLMClient):
    def generate_json(self, prompt: str) -> str:
        if "Classify each transaction" in prompt:
            return '{"classifications":[{"txn_id":"TXN2","category":"Food"}]}'
        return (
            '{"spend_by_currency":{"INR":"100.00","USD":"50.00"},'
            '"top_merchants":[{"merchant":"Swiggy","total":"50.00"}],'
            '"anomaly_count":1,'
            '"narrative":"Food spend includes one currency anomaly.",'
            '"risk_level":"medium"}'
        )


def build_session_factory() -> tuple[sessionmaker[Session], object]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), engine


def test_complete_pipeline_persists_results(tmp_path: Path) -> None:
    factory, engine = build_session_factory()
    csv_path = tmp_path / "transactions.csv"
    try:
        csv_path.write_text(
            "txn_id,date,merchant,amount,currency,status,category,account_id,notes\n"
            "TXN1,04-09-2024,Flipkart,100.00,INR,SUCCESS,Shopping,ACC1,\n"
            "TXN2,2024/02/05,Swiggy,50.00,USD,success,,ACC1,\n",
            encoding="utf-8",
        )
        with factory() as session:
            job = Job(
                filename="transactions.csv",
                storage_path=str(csv_path),
                status=JobStatus.PENDING,
                row_count_raw=2,
            )
            session.add(job)
            session.commit()
            job_id = job.id

        process_job(
            job_id,
            session_factory=factory,
            client_factory=lambda _: PipelineLLM(),
            settings=Settings(
                database_url="sqlite+pysqlite:///:memory:",
                redis_url="redis://localhost:6379/0",
                llm_retry_base_delay_seconds=0,
                upload_dir=tmp_path,
            ),
        )

        with factory() as session:
            job = session.get(Job, job_id)
            transactions = session.query(Transaction).order_by(Transaction.txn_id).all()

            assert job is not None
            assert job.status == JobStatus.COMPLETED
            assert job.row_count_clean == 2
            assert len(transactions) == 2
            assert transactions[1].category == "Food"
            assert transactions[1].is_anomaly is True
            assert job.summary is not None
            assert job.summary.risk_level == "medium"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
