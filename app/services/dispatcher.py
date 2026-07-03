from abc import ABC, abstractmethod
from uuid import UUID


class JobDispatchError(RuntimeError):
    pass


class JobDispatcher(ABC):
    @abstractmethod
    def dispatch(self, job_id: UUID) -> None:
        raise NotImplementedError


class CeleryJobDispatcher(JobDispatcher):
    def dispatch(self, job_id: UUID) -> None:
        try:
            from app.workers.tasks import process_transaction_job

            process_transaction_job.delay(str(job_id))
        except Exception as exc:
            raise JobDispatchError(
                "Unable to enqueue transaction processing job.",
            ) from exc
