from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import check_database_connection
from app.schemas.health import HealthResponse


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="alive")


@router.get("/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    try:
        check_database_connection()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    return HealthResponse(status="ready")