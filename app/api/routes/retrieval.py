from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_permission
from app.core.config import settings
from app.core.errors import (
    EmbeddingProviderError,
    PersistenceUnavailableError,
)
from app.db.session import get_db
from app.integrations.embeddings import OpenAIEmbeddingProvider
from app.models.user import User
from app.schemas.retrieval import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
)
from app.services.retrieval import RetrievalService


router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
)


require_knowledge_read = require_permission(
    "knowledge:read"
)


@router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
)
def search_knowledge(
    data: KnowledgeSearchRequest,
    current_user: Annotated[
        User,
        Depends(require_knowledge_read),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> KnowledgeSearchResponse:
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
    service = RetrievalService(
        db,
        provider,
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        chunk_size=settings.knowledge_chunk_size,
        chunk_overlap=settings.knowledge_chunk_overlap,
    )

    try:
        result = service.search(
            actor_user_id=current_user.id,
            request=data,
        )
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

    items = [
        KnowledgeSearchResult(
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            document_title=item.document_title,
            source_type=item.source_type,
            source_name=item.source_name,
            chunk_index=item.chunk_index,
            content=item.content,
            similarity=item.similarity,
        )
        for item in result.results
    ]

    return KnowledgeSearchResponse(
        results=items,
        result_count=len(items),
        embedding_model=result.embedding_model,
        embedding_dimensions=(
            result.embedding_dimensions
        ),
        token_usage=result.token_usage,
    )
