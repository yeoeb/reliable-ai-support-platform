from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import (
    InvalidToolCallingProviderResponseError,
    NoAuthorizedToolError,
)
from app.integrations.llm import ToolCallingProvider
from app.repositories.rbac import RBACRepository
from app.services.authorization import AuthorizationService
from app.services.tool_execution import ToolExecutionService
from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class AgentRunResult:
    answer: str
    tool_used: str | None
    tool_status: str | None
    model: str
    input_tokens: int
    output_tokens: int


class AgentService:
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
            return AgentRunResult(
                answer=choice.answer.strip(),
                tool_used=None,
                tool_status=None,
                model=choice.model,
                input_tokens=choice.input_tokens,
                output_tokens=choice.output_tokens,
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
        return AgentRunResult(
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
