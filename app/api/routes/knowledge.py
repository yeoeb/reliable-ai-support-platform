from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_permission
from app.core.errors import (
    EmbeddingProviderError,
    EmbeddingStateConflictError,
    InvalidKnowledgeContentError,
    KnowledgeDocumentNotFoundError,
    PersistenceUnavailableError,
)
from app.core.config import settings
from app.db.session import get_db
from app.integrations.embeddings import OpenAIEmbeddingProvider
from app.models.user import User
from app.schemas.embedding import KnowledgeEmbeddingRead
from app.schemas.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentRead,
)
from app.services.embedding import EmbeddingService
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



@router.post(
    "/documents/{document_id}/embeddings",
    response_model=KnowledgeEmbeddingRead,
    status_code=status.HTTP_200_OK,
)
def embed_knowledge_document(
    document_id: UUID,
    response: Response,
    current_user: Annotated[
        User,
        Depends(require_knowledge_manage),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> KnowledgeEmbeddingRead:
    api_key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key is not None
        else None
    )
    provider = OpenAIEmbeddingProvider(
        api_key=api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    service = EmbeddingService(
        db,
        provider,
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        embedding_batch_size=settings.embedding_batch_size,
        chunk_size=settings.knowledge_chunk_size,
        chunk_overlap=settings.knowledge_chunk_overlap,
    )

    try:
        result = service.embed_document(
            actor_user_id=current_user.id,
            document_id=document_id,
        )
    except KnowledgeDocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge document not found",
        ) from exc
    except EmbeddingStateConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Embedding state is inconsistent",
        ) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding service unavailable",
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

    return KnowledgeEmbeddingRead(
        document_id=result.document_id,
        embedding_provider=result.embedding_provider,
        embedding_model=result.embedding_model,
        embedding_dimensions=result.embedding_dimensions,
        chunk_count=result.chunk_count,
        embedding_config_hash=result.embedding_config_hash,
        changed=result.changed,
        token_usage=result.token_usage,
    )
