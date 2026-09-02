from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_permission
from app.core.errors import (
    InvalidKnowledgeContentError,
    PersistenceUnavailableError,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentRead,
)
from app.services.knowledge import KnowledgeService


router = APIRouter(
    prefix="/admin/knowledge",
    tags=["knowledge"],
)


require_knowledge_manage = require_permission(
    "knowledge:manage"
)


@router.post(
    "/documents",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_200_OK,
)
def ingest_knowledge_document(
    data: KnowledgeDocumentCreate,
    response: Response,
    current_user: Annotated[
        User,
        Depends(require_knowledge_manage),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> KnowledgeDocumentRead:
    service = KnowledgeService(db)

    try:
        result = service.ingest(
            actor_user_id=current_user.id,
            data=data,
        )
    except InvalidKnowledgeContentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Knowledge content is empty after normalization",
        ) from exc
    except PersistenceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistence service unavailable",
        ) from exc

    response.status_code = (
        status.HTTP_201_CREATED
        if result.changed
        else status.HTTP_200_OK
    )

    document = result.document
    return KnowledgeDocumentRead(
        id=document.id,
        title=document.title,
        source_type=document.source_type,
        source_name=document.source_name,
        content_hash=document.content_hash,
        created_at=document.created_at,
        changed=result.changed,
    )
