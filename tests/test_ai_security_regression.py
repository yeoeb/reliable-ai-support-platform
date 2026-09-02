from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.errors import (
    ApprovalStateConflictError,
    InvalidGenerationProviderResponseError,
    InvalidToolArgumentsError,
    NoAuthorizedToolError,
    UnknownToolError,
)
from app.evaluation.loader import load_results, load_suite
from app.evaluation.scorer import evaluate, thresholds_pass
from app.integrations.llm import (
    GroundedAnswerProviderResult,
    ToolCallRequest,
    ToolChoiceResult,
)
from app.schemas.rag import RagAnswerRequest
from app.services.agent import AgentService
from app.services.approval import ApprovalService
from app.services.rag import RagService
from app.services.retrieval import (
    KnowledgeSearchServiceResult,
    RetrievedKnowledge,
)
from app.tools.system import build_default_tool_registry


ROOT = Path(__file__).resolve().parents[1]
SECURITY_SUITE = (
    ROOT / "evals" / "suites" / "security-v1" / "suite.json"
)
SECURITY_RESULTS = (
    ROOT
    / "evals"
    / "suites"
    / "security-v1"
    / "baseline_results.jsonl"
)
NOW = datetime(
    2026,
    9,
    2,
    12,
    0,
    tzinfo=timezone.utc,
)


def test_security_v1_reuses_existing_scorer_and_passes_fixture() -> None:
    suite = load_suite(SECURITY_SUITE)
    results = load_results(SECURITY_RESULTS, suite)

    assert len(suite.cases) == 16
    assert all(case.safety_critical for case in suite.cases)

    report = evaluate(
        suite,
        results,
        candidate="security-baseline-v1",
    )

    assert report.total_cases == 16
    assert report.passed_cases == 16
    assert report.case_pass_rate == 1.0
    assert report.safety_violations == 0
    assert report.rag.total == 8
    assert report.tool.total == 8
    assert thresholds_pass(suite, report)


def test_security_v1_detects_unauthorized_tool_selection() -> None:
    suite = load_suite(SECURITY_SUITE)
    results = load_results(SECURITY_RESULTS, suite)

    changed = []
    for result in results:
        if result.case_id != (
            "tool-hidden-unauthorized-selection-denied"
        ):
            changed.append(result)
            continue
        payload = result.model_dump(mode="json")
        payload.update(
            {
                "decision": "tool_call",
                "tool_name": "dump_secrets",
                "arguments": {},
            }
        )
        changed.append(type(result).model_validate(payload))

    report = evaluate(
        suite,
        changed,
        candidate="hostile-tool",
    )

    assert report.tool.unauthorized_tool_calls == 1
    assert report.safety_violations == 1
    assert report.case_pass_rate < 1.0


def _rag_request() -> RagAnswerRequest:
    return RagAnswerRequest(
        question="ATTACK_PROMPT_SECRET_018",
        top_k=5,
        min_similarity=0.5,
    )


def _retrieved(
    content: str = "ATTACK_EVIDENCE_SECRET_018",
) -> RetrievedKnowledge:
    return RetrievedKnowledge(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Synthetic security document",
        source_type="markdown",
        source_name="security.md",
        chunk_index=0,
        content=content,
        similarity=0.95,
    )


def _rag_service(results):
    session = MagicMock(spec=Session)
    retrieval = MagicMock()
    retrieval.search.return_value = (
        KnowledgeSearchServiceResult(
            results=results,
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            token_usage=3,
        )
    )
    provider = MagicMock()
    service = RagService(session, retrieval, provider)
    service.audit_service = MagicMock()
    return service, session, provider


def test_zero_evidence_blocks_confident_hostile_provider() -> None:
    service, _, provider = _rag_service([])
    provider.generate.return_value = (
        GroundedAnswerProviderResult(
            answerable=True,
            answer="ATTACK_PROVIDER_SECRET_018",
            cited_source_ids=["S99"],
            input_tokens=1,
            output_tokens=1,
            model="synthetic-model",
        )
    )

    result = service.answer(
        actor_user_id=uuid4(),
        request=_rag_request(),
    )

    assert result.status == "insufficient_evidence"
    assert result.citations == []
    provider.generate.assert_not_called()


def test_hostile_evidence_and_forged_citation_fail_without_leak(
    monkeypatch,
) -> None:
    service, _, provider = _rag_service([_retrieved()])
    provider.generate.return_value = (
        GroundedAnswerProviderResult(
            answerable=True,
            answer="ATTACK_PROVIDER_SECRET_018",
            cited_source_ids=["S99"],
            input_tokens=1,
            output_tokens=1,
            model="synthetic-model",
        )
    )
    log_error = MagicMock()
    monkeypatch.setattr(
        "app.services.rag.logger.error",
        log_error,
    )

    with pytest.raises(
        InvalidGenerationProviderResponseError
    ):
        service.answer(
            actor_user_id=uuid4(),
            request=_rag_request(),
        )

    provider.generate.assert_called_once()
    log_extra = log_error.call_args.kwargs["extra"]
    audit_metadata = (
        service.audit_service.record_best_effort
        .call_args.kwargs["event_metadata"]
    )
    serialized = str(log_extra) + str(audit_metadata)

    for secret in (
        "ATTACK_PROMPT_SECRET_018",
        "ATTACK_EVIDENCE_SECRET_018",
        "ATTACK_PROVIDER_SECRET_018",
    ):
        assert secret not in serialized


def test_unanswerable_hostile_result_cannot_smuggle_citation() -> None:
    service, _, provider = _rag_service([_retrieved()])
    provider.generate.return_value = (
        GroundedAnswerProviderResult(
            answerable=False,
            answer="",
            cited_source_ids=["S1"],
            input_tokens=1,
            output_tokens=1,
            model="synthetic-model",
        )
    )

    with pytest.raises(
        InvalidGenerationProviderResponseError
    ):
        service.answer(
            actor_user_id=uuid4(),
            request=_rag_request(),
        )


def _tool_choice(name: str, arguments: dict) -> ToolChoiceResult:
    return ToolChoiceResult(
        answer=None,
        tool_call=ToolCallRequest(
            name=name,
            arguments=arguments,
        ),
        input_tokens=1,
        output_tokens=1,
        model="synthetic-model",
    )


def _agent_service(
    monkeypatch,
    *,
    permissions: set[str],
    choice: ToolChoiceResult,
):
    session = MagicMock(spec=Session)
    repository = MagicMock()
    repository.get_permission_names_for_user.return_value = (
        permissions
    )
    monkeypatch.setattr(
        "app.services.agent.RBACRepository",
        lambda session: repository,
    )
    provider = MagicMock()
    provider.choose.return_value = choice
    service = AgentService(
        session,
        build_default_tool_registry(),
        provider,
    )
    return service, session, provider


def test_hallucinated_tool_fails_before_any_side_effect(
    monkeypatch,
) -> None:
    service, _, provider = _agent_service(
        monkeypatch,
        permissions={"system:read"},
        choice=_tool_choice("shell", {}),
    )
    service.tool_execution = MagicMock()
    service.approval_service = MagicMock()

    with pytest.raises(UnknownToolError):
        service.run(
            actor_user_id=uuid4(),
            request="Run shell.",
        )

    service.tool_execution.execute.assert_not_called()
    service.approval_service.request_action.assert_not_called()
    provider.finalize.assert_not_called()


def test_read_only_argument_injection_fails_before_executor(
    monkeypatch,
) -> None:
    service, _, provider = _agent_service(
        monkeypatch,
        permissions={"system:read"},
        choice=_tool_choice(
            "platform_readiness",
            {"command": "whoami"},
        ),
    )
    definition = service.registry.get("platform_readiness")
    executor = MagicMock()
    object.__setattr__(definition, "executor", executor)

    with pytest.raises(InvalidToolArgumentsError):
        service.run(
            actor_user_id=uuid4(),
            request="ATTACK_PROMPT_SECRET_018",
        )

    executor.assert_not_called()
    provider.finalize.assert_not_called()


def test_admin_argument_injection_fails_before_approval_persistence(
    monkeypatch,
) -> None:
    target = uuid4()
    service, session, provider = _agent_service(
        monkeypatch,
        permissions={"rbac:manage"},
        choice=_tool_choice(
            "grant_support_agent_role",
            {
                "user_id": str(target),
                "role_name": "admin",
            },
        ),
    )
    service.approval_service.repository = MagicMock()
    definition = service.registry.get(
        "grant_support_agent_role"
    )
    approval_executor = MagicMock()
    object.__setattr__(
        definition,
        "approval_executor",
        approval_executor,
    )

    with pytest.raises(InvalidToolArgumentsError):
        service.run(
            actor_user_id=uuid4(),
            request="Grant admin.",
        )

    service.approval_service.repository.create.assert_not_called()
    approval_executor.assert_not_called()
    session.commit.assert_not_called()
    provider.finalize.assert_not_called()


def test_no_authorized_tools_bypasses_provider_and_actions(
    monkeypatch,
) -> None:
    service, _, provider = _agent_service(
        monkeypatch,
        permissions=set(),
        choice=_tool_choice("platform_readiness", {}),
    )
    service.tool_execution = MagicMock()
    service.approval_service = MagicMock()

    with pytest.raises(NoAuthorizedToolError):
        service.run(
            actor_user_id=uuid4(),
            request="Try any tool.",
        )

    provider.choose.assert_not_called()
    provider.finalize.assert_not_called()
    service.tool_execution.execute.assert_not_called()
    service.approval_service.request_action.assert_not_called()


def _pending_approval(
    *,
    tool_name="grant_support_agent_role",
    tool_arguments=None,
):
    return SimpleNamespace(
        id=uuid4(),
        requested_by_user_id=uuid4(),
        tool_name=tool_name,
        tool_arguments=(
            tool_arguments
            if tool_arguments is not None
            else {"user_id": str(uuid4())}
        ),
        status="pending",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
        decided_by_user_id=None,
        decided_at=None,
        executed_at=None,
    )


def _approval_service():
    session = MagicMock(spec=Session)
    registry = build_default_tool_registry()
    service = ApprovalService(session, registry)
    service.repository = MagicMock()
    service.audit_service = MagicMock()
    service.rbac_repository = MagicMock()
    service.rbac_repository.has_permission.return_value = True

    definition = registry.get("grant_support_agent_role")
    executor = MagicMock(
        return_value={"status": "assigned"}
    )
    object.__setattr__(
        definition,
        "approval_executor",
        executor,
    )
    return service, session, executor


def test_persisted_tool_name_tampering_fails_before_execution() -> None:
    service, session, executor = _approval_service()
    approval = _pending_approval(tool_name="shell")
    service.repository.get_for_update.return_value = approval

    with pytest.raises(ApprovalStateConflictError):
        service.approve(
            approval_id=approval.id,
            approver_user_id=uuid4(),
        )

    executor.assert_not_called()
    session.commit.assert_not_called()
    assert approval.status == "pending"


def test_persisted_admin_argument_tampering_fails_before_execution() -> None:
    service, session, executor = _approval_service()
    approval = _pending_approval(
        tool_arguments={
            "user_id": str(uuid4()),
            "role_name": "admin",
        }
    )
    service.repository.get_for_update.return_value = approval

    with pytest.raises(ApprovalStateConflictError):
        service.approve(
            approval_id=approval.id,
            approver_user_id=uuid4(),
        )

    executor.assert_not_called()
    session.commit.assert_not_called()
    assert approval.status == "pending"
