from fastapi import APIRouter, status

from app.schemas.health import HealthCheck

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthCheck, status_code=status.HTTP_200_OK)
def health_check() -> HealthCheck:
    return HealthCheck(status="ok", service="transaction-pipeline")
