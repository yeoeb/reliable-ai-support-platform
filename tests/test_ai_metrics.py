from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.errors import GenerationProviderUnavailableError
from app.integrations.llm import (
    GroundedAnswerProviderResult,
    ToolChoiceResult,
)
from app.schemas.rag import RagAnswerRequest
from app.services.agent import AgentRunResult, AgentService
from app.services.rag import RagService
from app.services.retrieval import (
    KnowledgeSearchServiceResult,
    RetrievedKnowledge,
)
from app.tools.system import build_default_tool_registry


def rag_request() -> RagAnswerRequest:
    return RagAnswerRequest(
        question="private question",
        top_k=5,
        min_similarity=0.5,
    )


def retrieved() -> RetrievedKnowledge:
    return RetrievedKnowledge(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Private title",
        source_type="markdown",
        source_name="private.md",
        chunk_index=0,
        content="private chunk",
        similarity=0.9,
    )


def rag_service(results):
    session = MagicMock(spec=Session)
    retrieval = MagicMock()
    retrieval.search.return_value = KnowledgeSearchServiceResult(
        results=results,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        token_usage=1,
    )
    provider = MagicMock()
    service = RagService(session, retrieval, provider)
    service.audit_service = MagicMock()
    return service, provider


def test_rag_grounded_records_bounded_outcome_and_tokens(
    monkeypatch,
) -> None:
    service, provider = rag_service([retrieved()])
    provider.generate.return_value = GroundedAnswerProviderResult(
        answerable=True,
        answer="bounded answer",
        cited_source_ids=["S1"],
        input_tokens=8,
        output_tokens=3,
        model="private-model-name",
    )
    metrics = MagicMock()
    monkeypatch.setattr(
        "app.services.rag.application_metrics",
        metrics,
    )

    result = service.answer(
        actor_user_id=uuid4(),
        request=rag_request(),
    )

    assert result.status == "grounded"
    metrics.record_ai_operation.assert_called_once_with(
        operation="rag_answer",
        outcome="grounded",
    )
    metrics.record_llm_tokens.assert_called_once_with(
        operation="rag_answer",
        input_tokens=8,
        output_tokens=3,
    )
    serialized = str(metrics.mock_calls)
    for secret in (
        "private question",
        "private chunk",
        "private-model-name",
    ):
        assert secret not in serialized


def test_rag_zero_evidence_records_outcome_without_tokens(
    monkeypatch,
) -> None:
    service, provider = rag_service([])
    metrics = MagicMock()
    monkeypatch.setattr(
        "app.services.rag.application_metrics",
        metrics,
    )

    result = service.answer(
        actor_user_id=uuid4(),
        request=rag_request(),
    )

    assert result.status == "insufficient_evidence"
    provider.generate.assert_not_called()
    metrics.record_ai_operation.assert_called_once_with(
        operation="rag_answer",
        outcome="insufficient_evidence",
    )
    metrics.record_llm_tokens.assert_called_once_with(
        operation="rag_answer",
        input_tokens=0,
        output_tokens=0,
    )


def test_rag_provider_failure_records_only_bounded_outcome(
    monkeypatch,
) -> None:
    service, provider = rag_service([retrieved()])
    provider.generate.side_effect = GenerationProviderUnavailableError()
    metrics = MagicMock()
    monkeypatch.setattr(
        "app.services.rag.application_metrics",
        metrics,
    )

    with pytest.raises(GenerationProviderUnavailableError):
        service.answer(
            actor_user_id=uuid4(),
            request=rag_request(),
        )

    metrics.record_ai_operation.assert_called_once_with(
        operation="rag_answer",
        outcome="provider_failure",
    )
    metrics.record_llm_tokens.assert_not_called()


def make_agent(monkeypatch, permissions):
    session = MagicMock(spec=Session)
    authorization = MagicMock()
    authorization.get_effective_permissions.return_value = permissions
    monkeypatch.setattr(
        "app.services.agent.AuthorizationService",
        lambda repo: authorization,
    )
    provider = MagicMock()
    service = AgentService(
        session,
        build_default_tool_registry(),
        provider,
    )
    service.tool_execution = MagicMock()
    return service, provider


def test_agent_completed_records_aggregate_tokens(
    monkeypatch,
) -> None:
    service, provider = make_agent(
        monkeypatch,
        {"system:read"},
    )
    provider.choose.return_value = ToolChoiceResult(
        answer="Done.",
        tool_call=None,
        input_tokens=4,
        output_tokens=2,
        model="private-model",
    )
    metrics = MagicMock()
    monkeypatch.setattr(
        "app.services.agent.application_metrics",
        metrics,
    )

    result = service.run(
        actor_user_id=uuid4(),
        request="private agent request",
    )

    assert result.status == "completed"
    metrics.record_ai_operation.assert_called_once_with(
        operation="agent_run",
        outcome="completed",
    )
    metrics.record_llm_tokens.assert_called_once_with(
        operation="agent_run",
        input_tokens=4,
        output_tokens=2,
    )
    assert "private agent request" not in str(metrics.mock_calls)
    assert "private-model" not in str(metrics.mock_calls)


def test_agent_approval_required_records_bounded_tokens(
    monkeypatch,
) -> None:
    service, provider = make_agent(
        monkeypatch,
        {"rbac:manage"},
    )
    target = uuid4()
    approval_id = uuid4()
    from app.integrations.llm import ToolCallRequest

    provider.choose.return_value = ToolChoiceResult(
        answer=None,
        tool_call=ToolCallRequest(
            name="grant_support_agent_role",
            arguments={"user_id": str(target)},
        ),
        input_tokens=5,
        output_tokens=2,
        model="private-model",
    )
    service.approval_service = MagicMock()
    service.approval_service.request_action.return_value = (
        SimpleNamespace(id=approval_id)
    )
    metrics = MagicMock()
    monkeypatch.setattr(
        "app.services.agent.application_metrics",
        metrics,
    )

    result = service.run(
        actor_user_id=uuid4(),
        request="private approval request",
    )

    assert result.status == "approval_required"
    metrics.record_ai_operation.assert_called_once_with(
        operation="agent_run",
        outcome="approval_required",
    )
    metrics.record_llm_tokens.assert_called_once_with(
        operation="agent_run",
        input_tokens=5,
        output_tokens=2,
    )
    assert str(target) not in str(metrics.mock_calls)
