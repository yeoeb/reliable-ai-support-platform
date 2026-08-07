from fastapi import APIRouter

from app.schemas.health import HealthResponse


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def liveness_check() -> HealthResponse:
    return HealthResponse(status="alive")


@router.get("/ready", response_model=HealthResponse)
def readiness_check() -> HealthResponse:
    return HealthResponse(status="ready")