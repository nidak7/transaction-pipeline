from collections.abc import Callable
from typing import Any, TypeVar

try:
    from celery import Celery
except ModuleNotFoundError:
    F = TypeVar("F", bound=Callable[..., Any])

    class Celery:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.conf: dict[str, Any] = {}

        def task(self, **_kwargs: Any) -> Callable[[F], F]:
            def decorator(function: F) -> F:
                function.delay = function  # type: ignore[attr-defined]
                return function

            return decorator


from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "transaction_pipeline",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    accept_content=["json"],
    result_serializer="json",
    task_serializer="json",
    task_track_started=True,
    timezone="UTC",
)
