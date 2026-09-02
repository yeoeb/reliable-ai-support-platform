from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST

from app.core.metrics import application_metrics


router = APIRouter()


@router.get(
    "/metrics",
    include_in_schema=False,
)
def metrics() -> Response:
    return Response(
        content=application_metrics.exposition(),
        status_code=200,
        headers={
            "Content-Type": CONTENT_TYPE_LATEST,
        },
    )
