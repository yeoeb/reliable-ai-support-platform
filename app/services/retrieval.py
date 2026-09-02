from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import (
    EmbeddingProviderError,
    InvalidEmbeddingProviderResponseError,
    PersistenceUnavailableError,
)
from app.integrations.embeddings import (
    EmbeddingBatchResult,
    EmbeddingProvider,
)
from app.repositories.retrieval import RetrievalRepository
from app.schemas.retrieval import KnowledgeSearchRequest
from app.services.audit import AuditService
from app.services.chunking import build_embedding_pipeline_config


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedKnowledge:
    chunk_id: UUID
    document_id: UUID
    document_title: str
    source_type: str
    source_name: str
    chunk_index: int
    content: str
    similarity: float


@dataclass(frozen=True)
class KnowledgeSearchServiceResult:
    results: list[RetrievedKnowledge]
    embedding_model: str
    embedding_dimensions: int
    token_usage: int


class RetrievalService:
    def __init__(
        self,
        session: Session,
        provider: EmbeddingProvider,
        *,
        embedding_model: str,
        embedding_dimensions: int,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self.session = session
        self.provider = provider
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self.repository = RetrievalRepository(
            session
        )
        self.audit_service = AuditService(
            session
        )

    def _config_hash(self) -> str:
        return build_embedding_pipeline_config(
            provider_name=self.provider.provider_name,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            embedding_model=self.embedding_model,
            embedding_dimensions=self.embedding_dimensions,
        ).config_hash

    def _validate_query_embedding(
        self,
        result: EmbeddingBatchResult,
    ) -> tuple[list[float], int]:
        try:
            vectors = result.vectors
            token_usage = result.token_usage

            if len(vectors) != 1:
                raise InvalidEmbeddingProviderResponseError(
                    "Embedding provider returned an unexpected item count"
                )

            vector = vectors[0]

            if len(vector) != self.embedding_dimensions:
                raise InvalidEmbeddingProviderResponseError(
                    "Embedding provider returned an invalid dimension"
                )

            if not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in vector
            ):
                raise InvalidEmbeddingProviderResponseError(
                    "Embedding provider returned an invalid vector value"
                )

            norm_squared = math.fsum(
                float(value) * float(value)
                for value in vector
            )
            if norm_squared <= 0.0:
                raise InvalidEmbeddingProviderResponseError(
                    "Embedding provider returned a zero query vector"
                )

            if (
                not isinstance(token_usage, int)
                or isinstance(token_usage, bool)
                or token_usage < 0
            ):
                raise InvalidEmbeddingProviderResponseError(
                    "Embedding provider returned invalid token usage"
                )

            return [
                float(value)
                for value in vector
            ], token_usage

        except InvalidEmbeddingProviderResponseError:
            raise
        except (
            AttributeError,
            TypeError,
        ) as exc:
            raise InvalidEmbeddingProviderResponseError(
                "Embedding provider returned a malformed result"
            ) from exc

    @staticmethod
    def _similarity(
        cosine_distance: float,
    ) -> float:
        similarity = 1.0 - cosine_distance
        return max(
            -1.0,
            min(1.0, similarity),
        )

    def search(
        self,
        *,
        actor_user_id: UUID,
        request: KnowledgeSearchRequest,
    ) -> KnowledgeSearchServiceResult:
        config_hash = self._config_hash()

        # Authorization dependencies may have opened a read transaction
        # on this shared request Session. Close it before waiting on the
        # external Embedding Provider.
        self.session.rollback()

        try:
            provider_result = self.provider.embed(
                [request.query]
            )
            query_vector, token_usage = (
                self._validate_query_embedding(
                    provider_result
                )
            )
        except EmbeddingProviderError:
            raise

        try:
            rows = self.repository.search_exact_cosine(
                query_vector=query_vector,
                embedding_config_hash=config_hash,
                top_k=request.top_k,
                min_similarity=request.min_similarity,
            )
        except SQLAlchemyError as exc:
            self.session.rollback()

            logger.error(
                "Knowledge retrieval persistence failed",
                extra={
                    "event": (
                        "knowledge.search."
                        "persistence_failure"
                    ),
                    "top_k": request.top_k,
                    "min_similarity": (
                        request.min_similarity
                    ),
                    "embedding_model": (
                        self.embedding_model
                    ),
                    "embedding_dimensions": (
                        self.embedding_dimensions
                    ),
                },
            )

            raise PersistenceUnavailableError from exc

        results = [
            RetrievedKnowledge(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                document_title=row.document_title,
                source_type=row.source_type,
                source_name=row.source_name,
                chunk_index=row.chunk_index,
                content=row.content,
                similarity=self._similarity(
                    row.cosine_distance
                ),
            )
            for row in rows
        ]

        self.audit_service.record_best_effort(
            actor_user_id=actor_user_id,
            action="knowledge.search",
            target_type="knowledge",
            target_id=config_hash,
            outcome="success",
            event_metadata={
                "top_k": request.top_k,
                "min_similarity": (
                    request.min_similarity
                ),
                "result_count": len(results),
                "embedding_model": (
                    self.embedding_model
                ),
                "embedding_dimensions": (
                    self.embedding_dimensions
                ),
                "token_usage": token_usage,
            },
        )

        logger.info(
            "Knowledge search completed",
            extra={
                "event": "knowledge.search.completed",
                "result_count": len(results),
                "top_k": request.top_k,
                "min_similarity": (
                    request.min_similarity
                ),
                "embedding_model": (
                    self.embedding_model
                ),
                "embedding_dimensions": (
                    self.embedding_dimensions
                ),
                "token_usage": token_usage,
            },
        )

        return KnowledgeSearchServiceResult(
            results=results,
            embedding_model=self.embedding_model,
            embedding_dimensions=(
                self.embedding_dimensions
            ),
            token_usage=token_usage,
        )
