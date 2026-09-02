from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.metrics import application_metrics
from app.core.errors import (
    InvalidToolCallingProviderResponseError,
    NoAuthorizedToolError,
)
from app.integrations.llm import ToolCallingProvider
from app.repositories.rbac import RBACRepository
from app.services.approval import ApprovalService
from app.services.authorization import AuthorizationService
from app.services.tool_execution import ToolExecutionService
from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class AgentRunResult:
    status: str
    approval_id: UUID | None
    answer: str
    tool_used: str | None
    tool_status: str | None
    model: str
    input_tokens: int
    output_tokens: int


class AgentService:
    @staticmethod
    def _record_result(
        result: AgentRunResult,
    ) -> AgentRunResult:
        application_metrics.record_ai_operation(
            operation="agent_run",
            outcome=result.status,
        )
        application_metrics.record_llm_tokens(
            operation="agent_run",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        return result

    def __init__(
        self,
        session: Session,
        registry: ToolRegistry,
        provider: ToolCallingProvider,
    ) -> None:
        self.session = session
        self.registry = registry
        self.provider = provider
        self.tool_execution = ToolExecutionService(
            session,
            registry,
        )
        self.approval_service = ApprovalService(
            session,
            registry,
        )

    def run(
        self,
        *,
        actor_user_id: UUID,
        request: str,
    ) -> AgentRunResult:
        authorization = AuthorizationService(
            RBACRepository(self.session)
        )
        permissions = authorization.get_effective_permissions(
            actor_user_id
        )
        allowed = self.registry.authorized_for_permissions(
            permissions
        )
        self.session.rollback()

        if not allowed:
            raise NoAuthorizedToolError(
                "Caller has no authorized tools"
            )

        choice = self.provider.choose(
            request=request,
            tools=[
                definition.provider_spec()
                for definition in allowed
            ],
        )

        if choice.tool_call is None:
            if (
                not isinstance(choice.answer, str)
                or not choice.answer.strip()
            ):
                raise InvalidToolCallingProviderResponseError(
                    "Tool provider returned invalid direct answer"
                )
            return self._record_result(
                AgentRunResult(
                    status="completed",
                    approval_id=None,
                    answer=choice.answer.strip(),
                    tool_used=None,
                    tool_status=None,
                    model=choice.model,
                    input_tokens=choice.input_tokens,
                    output_tokens=choice.output_tokens,
                )
            )

        definition = self.registry.get(
            choice.tool_call.name
        )

        if definition.risk_level == "approval_required":
            approval = self.approval_service.request_action(
                actor_user_id=actor_user_id,
                tool_name=choice.tool_call.name,
                arguments=choice.tool_call.arguments,
            )
            return self._record_result(
                AgentRunResult(
                    status="approval_required",
                    approval_id=approval.id,
                    answer="Human approval required.",
                    tool_used=choice.tool_call.name,
                    tool_status="approval_required",
                    model=choice.model,
                    input_tokens=choice.input_tokens,
                    output_tokens=choice.output_tokens,
                )
            )

        result = self.tool_execution.execute(
            actor_user_id=actor_user_id,
            tool_name=choice.tool_call.name,
            arguments=choice.tool_call.arguments,
        )

        final = self.provider.finalize(
            request=request,
            tool_name=choice.tool_call.name,
            tool_result=result,
        )
        return self._record_result(
            AgentRunResult(
                status="completed",
                approval_id=None,
                answer=final.answer,
                tool_used=choice.tool_call.name,
                tool_status=result["status"],
                model=final.model,
                input_tokens=(
                    choice.input_tokens
                    + final.input_tokens
                ),
                output_tokens=(
                    choice.output_tokens
                    + final.output_tokens
                ),
            )
        )
