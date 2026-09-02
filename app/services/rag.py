from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import (
    GenerationProviderError,
    InvalidGenerationProviderResponseError,
)
from app.integrations.llm import (
    GroundedAnswerProvider,
    GroundedAnswerProviderResult,
    GroundedSource,
)
from app.schemas.rag import RagAnswerRequest
from app.schemas.retrieval import KnowledgeSearchRequest
from app.services.audit import AuditService
from app.services.retrieval import (
    RetrievalService,
    RetrievedKnowledge,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RagCitationResult:
    source_id: str
    chunk_id: UUID
    document_id: UUID
    document_title: str
    source_type: str
    source_name: str
    chunk_index: int
    similarity: float
    content: str


@dataclass(frozen=True)
class RagAnswerServiceResult:
    status: str
    answer: str
    citations: list[RagCitationResult]
    generation_model: str | None
    input_tokens: int
    output_tokens: int


class RagService:
    def __init__(
        self,
        session: Session,
        retrieval_service: RetrievalService,
        provider: GroundedAnswerProvider,
    ) -> None:
        self.session = session
        self.retrieval_service = retrieval_service
        self.provider = provider
        self.audit_service = AuditService(session)

    @staticmethod
    def _source_map(
        results: list[RetrievedKnowledge],
    ) -> dict[str, RetrievedKnowledge]:
        return {
            f"S{index}": result
            for index, result in enumerate(results, start=1)
        }

    @staticmethod
    def _validate_provider_result(
        result: GroundedAnswerProviderResult,
        source_map: dict[str, RetrievedKnowledge],
    ) -> tuple[str, list[str]]:
        if not isinstance(result.answerable, bool):
            raise InvalidGenerationProviderResponseError(
                "Generation provider returned invalid answerable flag"
            )
        if (
            not isinstance(result.answer, str)
            or (
                result.answerable
                and not result.answer.strip()
            )
        ):
            raise InvalidGenerationProviderResponseError(
                "Generation provider returned invalid answer"
            )
        if (
            not isinstance(result.cited_source_ids, list)
            or not all(
                isinstance(item, str) and item
                for item in result.cited_source_ids
            )
        ):
            raise InvalidGenerationProviderResponseError(
                "Generation provider returned invalid citations"
            )
        if (
            not isinstance(result.input_tokens, int)
            or isinstance(result.input_tokens, bool)
            or result.input_tokens < 0
            or not isinstance(result.output_tokens, int)
            or isinstance(result.output_tokens, bool)
            or result.output_tokens < 0
            or not isinstance(result.model, str)
            or not result.model.strip()
        ):
            raise InvalidGenerationProviderResponseError(
                "Generation provider returned invalid metadata"
            )

        normalized_ids = list(
            dict.fromkeys(result.cited_source_ids)
        )

        unknown = [
            source_id
            for source_id in normalized_ids
            if source_id not in source_map
        ]
        if unknown:
            raise InvalidGenerationProviderResponseError(
                "Generation provider cited an unknown source"
            )

        if result.answerable and not normalized_ids:
            raise InvalidGenerationProviderResponseError(
                "Grounded answer requires at least one citation"
            )
        if not result.answerable and normalized_ids:
            raise InvalidGenerationProviderResponseError(
                "Insufficient-evidence answer must not cite sources"
            )

        return result.answer.strip(), normalized_ids

    def _record_outcome(
        self,
        *,
        actor_user_id: UUID,
        request: RagAnswerRequest,
        status: str,
        retrieved_count: int,
        citation_count: int,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
        outcome: str = "success",
    ) -> None:
        metadata = {
            "status": status,
            "retrieved_count": retrieved_count,
            "citation_count": citation_count,
            "top_k": request.top_k,
            "min_similarity": request.min_similarity,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

        self.audit_service.record_best_effort(
            actor_user_id=actor_user_id,
            action="knowledge.answer",
            target_type="knowledge",
            target_id=None,
            outcome=outcome,
            event_metadata=metadata,
        )

        logger.info(
            "Grounded knowledge answer completed",
            extra={
                "event": "knowledge.answer.completed",
                **metadata,
            },
        )

    def answer(
        self,
        *,
        actor_user_id: UUID,
        request: RagAnswerRequest,
    ) -> RagAnswerServiceResult:
        retrieval = self.retrieval_service.search(
            actor_user_id=actor_user_id,
            request=KnowledgeSearchRequest(
                query=request.question,
                top_k=request.top_k,
                min_similarity=request.min_similarity,
            ),
        )

        if not retrieval.results:
            self._record_outcome(
                actor_user_id=actor_user_id,
                request=request,
                status="insufficient_evidence",
                retrieved_count=0,
                citation_count=0,
                model=None,
                input_tokens=0,
                output_tokens=0,
            )
            return RagAnswerServiceResult(
                status="insufficient_evidence",
                answer="Insufficient evidence.",
                citations=[],
                generation_model=None,
                input_tokens=0,
                output_tokens=0,
            )

        source_map = self._source_map(
            retrieval.results
        )
        sources = [
            GroundedSource(
                source_id=source_id,
                content=result.content,
            )
            for source_id, result in source_map.items()
        ]

        # Retrieval/Audit may have used the shared request Session. Ensure
        # no read transaction is intentionally held while waiting on the
        # external generation Provider.
        self.session.rollback()

        try:
            provider_result = self.provider.generate(
                question=request.question,
                sources=sources,
            )
            answer, source_ids = (
                self._validate_provider_result(
                    provider_result,
                    source_map,
                )
            )
        except GenerationProviderError:
            logger.error(
                "Grounded knowledge answer provider failed",
                extra={
                    "event": "knowledge.answer.provider_failure",
                    "retrieved_count": len(retrieval.results),
                    "top_k": request.top_k,
                    "min_similarity": request.min_similarity,
                },
            )
            self.audit_service.record_best_effort(
                actor_user_id=actor_user_id,
                action="knowledge.answer",
                target_type="knowledge",
                target_id=None,
                outcome="failure",
                event_metadata={
                    "status": "provider_failure",
                    "retrieved_count": len(retrieval.results),
                    "top_k": request.top_k,
                    "min_similarity": request.min_similarity,
                },
            )
            raise

        if not provider_result.answerable:
            self._record_outcome(
                actor_user_id=actor_user_id,
                request=request,
                status="insufficient_evidence",
                retrieved_count=len(retrieval.results),
                citation_count=0,
                model=provider_result.model,
                input_tokens=provider_result.input_tokens,
                output_tokens=provider_result.output_tokens,
            )
            return RagAnswerServiceResult(
                status="insufficient_evidence",
                answer="Insufficient evidence.",
                citations=[],
                generation_model=provider_result.model,
                input_tokens=provider_result.input_tokens,
                output_tokens=provider_result.output_tokens,
            )

        citations = [
            RagCitationResult(
                source_id=source_id,
                chunk_id=source_map[source_id].chunk_id,
                document_id=source_map[source_id].document_id,
                document_title=source_map[source_id].document_title,
                source_type=source_map[source_id].source_type,
                source_name=source_map[source_id].source_name,
                chunk_index=source_map[source_id].chunk_index,
                similarity=source_map[source_id].similarity,
                content=source_map[source_id].content,
            )
            for source_id in source_ids
        ]

        self._record_outcome(
            actor_user_id=actor_user_id,
            request=request,
            status="grounded",
            retrieved_count=len(retrieval.results),
            citation_count=len(citations),
            model=provider_result.model,
            input_tokens=provider_result.input_tokens,
            output_tokens=provider_result.output_tokens,
        )

        return RagAnswerServiceResult(
            status="grounded",
            answer=answer,
            citations=citations,
            generation_model=provider_result.model,
            input_tokens=provider_result.input_tokens,
            output_tokens=provider_result.output_tokens,
        )
