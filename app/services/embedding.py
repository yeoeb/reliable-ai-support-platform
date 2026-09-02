from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import (
    EmbeddingProviderError,
    EmbeddingStateConflictError,
    InvalidEmbeddingProviderResponseError,
    KnowledgeDocumentNotFoundError,
    PersistenceUnavailableError,
)
from app.integrations.embeddings import (
    EmbeddingBatchResult,
    EmbeddingProvider,
)
from app.repositories.embedding import (
    EmbeddingRepository,
    KnowledgeChunkCreateRecord,
    PersistedChunkState,
)
from app.repositories.knowledge import KnowledgeRepository
from app.services.audit import AuditService
from app.services.chunking import (
    EmbeddingPipelineConfig,
    TextChunk,
    build_embedding_pipeline_config,
    split_into_chunks,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeEmbeddingResult:
    document_id: UUID
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    chunk_count: int
    embedding_config_hash: str
    changed: bool
    token_usage: int


class EmbeddingService:
    def __init__(
        self,
        session: Session,
        provider: EmbeddingProvider,
        *,
        embedding_model: str,
        embedding_dimensions: int,
        embedding_batch_size: int,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        if not 1 <= embedding_batch_size <= 32:
            raise ValueError(
                "embedding_batch_size must be between 1 and 32"
            )

        self.session = session
        self.provider = provider
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self.embedding_batch_size = embedding_batch_size
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self.knowledge_repository = KnowledgeRepository(
            session
        )
        self.embedding_repository = EmbeddingRepository(
            session
        )
        self.audit_service = AuditService(session)

    def _pipeline_config(
        self,
    ) -> EmbeddingPipelineConfig:
        return build_embedding_pipeline_config(
            provider_name=self.provider.provider_name,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            embedding_model=self.embedding_model,
            embedding_dimensions=self.embedding_dimensions,
        )

    def _classify_existing(
        self,
        states: list[PersistedChunkState],
        expected_chunks: list[TextChunk],
        config: EmbeddingPipelineConfig,
    ) -> str:
        if not states:
            return "missing"

        if len(states) != len(expected_chunks):
            return "inconsistent"

        for state, expected in zip(
            states,
            expected_chunks,
            strict=True,
        ):
            if state.chunk_index != expected.index:
                return "inconsistent"

            if state.content_hash != expected.content_hash:
                return "inconsistent"

            if (
                state.embedding_provider
                != config.provider_name
                or state.embedding_model
                != config.embedding_model
                or state.embedding_dimensions
                != config.embedding_dimensions
                or state.chunking_strategy
                != config.chunking_strategy
                or state.chunk_size
                != config.chunk_size
                or state.chunk_overlap
                != config.chunk_overlap
                or state.embedding_config_hash
                != config.config_hash
            ):
                return "inconsistent"

        return "complete"

    def _embed_chunks(
        self,
        chunks: list[TextChunk],
    ) -> tuple[list[list[float]], int]:
        all_vectors: list[list[float]] = []
        total_tokens = 0

        for start in range(
            0,
            len(chunks),
            self.embedding_batch_size,
        ):
            batch = chunks[
                start : start
                + self.embedding_batch_size
            ]

            result = self.provider.embed(
                [
                    chunk.content
                    for chunk in batch
                ]
            )

            self._validate_provider_result(
                result,
                expected_count=len(batch),
            )

            all_vectors.extend(result.vectors)
            total_tokens += result.token_usage

        return all_vectors, total_tokens

    def _validate_provider_result(
        self,
        result: EmbeddingBatchResult,
        *,
        expected_count: int,
    ) -> None:
        if len(result.vectors) != expected_count:
            raise InvalidEmbeddingProviderResponseError(
                "Embedding provider returned an unexpected item count"
            )

        for vector in result.vectors:
            if len(vector) != self.embedding_dimensions:
                raise InvalidEmbeddingProviderResponseError(
                    "Embedding provider returned an invalid dimension"
                )

            if not all(
                isinstance(value, (int, float))
                and math.isfinite(float(value))
                for value in vector
            ):
                raise InvalidEmbeddingProviderResponseError(
                    "Embedding provider returned an invalid vector value"
                )

        if result.token_usage < 0:
            raise InvalidEmbeddingProviderResponseError(
                "Embedding provider returned invalid token usage"
            )

    def _records(
        self,
        *,
        document_id: UUID,
        chunks: list[TextChunk],
        vectors: list[list[float]],
        config: EmbeddingPipelineConfig,
    ) -> list[KnowledgeChunkCreateRecord]:
        return [
            KnowledgeChunkCreateRecord(
                document_id=document_id,
                chunk_index=chunk.index,
                content=chunk.content,
                content_hash=chunk.content_hash,
                embedding=vector,
                embedding_provider=config.provider_name,
                embedding_model=config.embedding_model,
                embedding_dimensions=config.embedding_dimensions,
                chunking_strategy=config.chunking_strategy,
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
                embedding_config_hash=config.config_hash,
            )
            for chunk, vector in zip(
                chunks,
                vectors,
                strict=True,
            )
        ]

    def _record_audit(
        self,
        *,
        actor_user_id: UUID,
        document_id: UUID,
        config: EmbeddingPipelineConfig,
        chunk_count: int,
        changed: bool,
        token_usage: int,
    ) -> None:
        self.audit_service.record(
            actor_user_id=actor_user_id,
            action="knowledge.document.embed",
            target_type="knowledge_document",
            target_id=str(document_id),
            outcome="success",
            event_metadata={
                "embedding_provider": config.provider_name,
                "embedding_model": config.embedding_model,
                "embedding_dimensions": config.embedding_dimensions,
                "chunk_count": chunk_count,
                "embedding_config_hash": config.config_hash,
                "changed": changed,
                "token_usage": token_usage,
            },
        )

    def _finish(
        self,
        *,
        document_id: UUID,
        config: EmbeddingPipelineConfig,
        chunk_count: int,
        changed: bool,
        token_usage: int,
    ) -> KnowledgeEmbeddingResult:
        logger.info(
            "Knowledge document embedded",
            extra={
                "event": "knowledge.document.embedded",
                "document_id": str(document_id),
                "embedding_provider": config.provider_name,
                "embedding_model": config.embedding_model,
                "embedding_dimensions": config.embedding_dimensions,
                "chunk_count": chunk_count,
                "changed": changed,
                "token_usage": token_usage,
            },
        )

        return KnowledgeEmbeddingResult(
            document_id=document_id,
            embedding_provider=config.provider_name,
            embedding_model=config.embedding_model,
            embedding_dimensions=config.embedding_dimensions,
            chunk_count=chunk_count,
            embedding_config_hash=config.config_hash,
            changed=changed,
            token_usage=token_usage,
        )

    def _commit_existing_action(
        self,
        *,
        actor_user_id: UUID,
        document_id: UUID,
        config: EmbeddingPipelineConfig,
        chunk_count: int,
        token_usage: int,
    ) -> KnowledgeEmbeddingResult:
        try:
            self._record_audit(
                actor_user_id=actor_user_id,
                document_id=document_id,
                config=config,
                chunk_count=chunk_count,
                changed=False,
                token_usage=token_usage,
            )
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise PersistenceUnavailableError from exc

        return self._finish(
            document_id=document_id,
            config=config,
            chunk_count=chunk_count,
            changed=False,
            token_usage=token_usage,
        )

    def embed_document(
        self,
        *,
        actor_user_id: UUID,
        document_id: UUID,
    ) -> KnowledgeEmbeddingResult:
        document = self.knowledge_repository.get_by_id(
            document_id
        )

        if document is None:
            self.session.rollback()
            raise KnowledgeDocumentNotFoundError

        document_snapshot_id = document.id
        document_content = document.content

        chunks = split_into_chunks(
            document_content,
            chunk_size=self.chunk_size,
            overlap=self.chunk_overlap,
        )
        config = self._pipeline_config()

        initial_states = (
            self.embedding_repository
            .list_states_for_config(
                document_id=document_snapshot_id,
                embedding_config_hash=config.config_hash,
            )
        )
        initial_state = self._classify_existing(
            initial_states,
            chunks,
            config,
        )

        # End the read-only transaction before any external API wait.
        self.session.rollback()

        if initial_state == "complete":
            return self._commit_existing_action(
                actor_user_id=actor_user_id,
                document_id=document_snapshot_id,
                config=config,
                chunk_count=len(chunks),
                token_usage=0,
            )

        if initial_state == "inconsistent":
            raise EmbeddingStateConflictError

        try:
            vectors, token_usage = self._embed_chunks(
                chunks
            )
        except EmbeddingProviderError:
            raise

        try:
            current_states = (
                self.embedding_repository
                .list_states_for_config(
                    document_id=document_snapshot_id,
                    embedding_config_hash=config.config_hash,
                )
            )
            current_state = self._classify_existing(
                current_states,
                chunks,
                config,
            )

            if current_state == "complete":
                self._record_audit(
                    actor_user_id=actor_user_id,
                    document_id=document_snapshot_id,
                    config=config,
                    chunk_count=len(chunks),
                    changed=False,
                    token_usage=token_usage,
                )
                self.session.commit()

                return self._finish(
                    document_id=document_snapshot_id,
                    config=config,
                    chunk_count=len(chunks),
                    changed=False,
                    token_usage=token_usage,
                )

            if current_state == "inconsistent":
                self.session.rollback()
                raise EmbeddingStateConflictError

            records = self._records(
                document_id=document_snapshot_id,
                chunks=chunks,
                vectors=vectors,
                config=config,
            )

            self.embedding_repository.create_many(
                records
            )

            self._record_audit(
                actor_user_id=actor_user_id,
                document_id=document_snapshot_id,
                config=config,
                chunk_count=len(chunks),
                changed=True,
                token_usage=token_usage,
            )

            self.session.commit()

            return self._finish(
                document_id=document_snapshot_id,
                config=config,
                chunk_count=len(chunks),
                changed=True,
                token_usage=token_usage,
            )

        except IntegrityError as exc:
            self.session.rollback()

            resolved_states = (
                self.embedding_repository
                .list_states_for_config(
                    document_id=document_snapshot_id,
                    embedding_config_hash=config.config_hash,
                )
            )
            resolved_state = self._classify_existing(
                resolved_states,
                chunks,
                config,
            )

            self.session.rollback()

            if resolved_state == "complete":
                return self._commit_existing_action(
                    actor_user_id=actor_user_id,
                    document_id=document_snapshot_id,
                    config=config,
                    chunk_count=len(chunks),
                    token_usage=token_usage,
                )

            if resolved_state == "inconsistent":
                raise EmbeddingStateConflictError from exc

            raise PersistenceUnavailableError from exc

        except SQLAlchemyError as exc:
            self.session.rollback()

            logger.error(
                "Embedding persistence failed",
                extra={
                    "event": (
                        "knowledge.document."
                        "embedding_persistence_failure"
                    ),
                    "document_id": str(
                        document_snapshot_id
                    ),
                    "embedding_provider": config.provider_name,
                    "embedding_model": config.embedding_model,
                    "embedding_dimensions": (
                        config.embedding_dimensions
                    ),
                    "chunk_count": len(chunks),
                },
            )

            raise PersistenceUnavailableError from exc
