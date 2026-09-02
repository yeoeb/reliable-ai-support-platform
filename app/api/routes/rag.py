from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_permission
from app.core.config import settings
from app.core.errors import (
    EmbeddingProviderError,
    GenerationProviderError,
    PersistenceUnavailableError,
)
from app.db.session import get_db
from app.integrations.embeddings import OpenAIEmbeddingProvider
from app.integrations.llm import OpenAIGroundedAnswerProvider
from app.models.user import User
from app.schemas.rag import (
    RagAnswerRequest,
    RagAnswerResponse,
    RagCitation,
)
from app.services.rag import RagService
from app.services.retrieval import RetrievalService


router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
)

require_knowledge_read = require_permission(
    "knowledge:read"
)


@router.post(
    "/answer",
    response_model=RagAnswerResponse,
)
def answer_knowledge(
    data: RagAnswerRequest,
    current_user: Annotated[
        User,
        Depends(require_knowledge_read),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> RagAnswerResponse:
    api_key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key is not None
        else None
    )

    embedding_provider = OpenAIEmbeddingProvider(
        api_key=api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    retrieval_service = RetrievalService(
        db,
        embedding_provider,
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        chunk_size=settings.knowledge_chunk_size,
        chunk_overlap=settings.knowledge_chunk_overlap,
    )
    generation_provider = OpenAIGroundedAnswerProvider(
        api_key=api_key,
        model=settings.rag_model,
        max_output_tokens=settings.rag_max_output_tokens,
    )
    service = RagService(
        db,
        retrieval_service,
        generation_provider,
    )

    try:
        result = service.answer(
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
    except GenerationProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Generation service unavailable",
        ) from exc

    return RagAnswerResponse(
        status=result.status,
        answer=result.answer,
        citations=[
            RagCitation(
                source_id=item.source_id,
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                document_title=item.document_title,
                source_type=item.source_type,
                source_name=item.source_name,
                chunk_index=item.chunk_index,
                similarity=item.similarity,
                content=item.content,
            )
            for item in result.citations
        ],
        generation_model=result.generation_model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
