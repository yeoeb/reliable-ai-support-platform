from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.core.config import settings
from app.core.errors import (
    InvalidToolArgumentsError,
    InvalidToolCallingProviderResponseError,
    NoAuthorizedToolError,
    PersistenceUnavailableError,
    ToolCallingProviderError,
    ToolExecutionError,
    ToolPermissionDeniedError,
    UnknownToolError,
)
from app.db.session import get_db
from app.integrations.llm import OpenAIToolCallingProvider
from app.models.user import User
from app.schemas.agent import AgentRunRequest, AgentRunResponse
from app.services.agent import AgentService
from app.tools.system import build_default_tool_registry


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post(
    "/run",
    response_model=AgentRunResponse,
)
def run_agent(
    data: AgentRunRequest,
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> AgentRunResponse:
    api_key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key is not None
        else None
    )
    provider = OpenAIToolCallingProvider(
        api_key=api_key,
        model=settings.rag_model,
        max_output_tokens=settings.rag_max_output_tokens,
    )
    service = AgentService(
        db,
        build_default_tool_registry(),
        provider,
    )

    try:
        result = service.run(
            actor_user_id=current_user.id,
            request=data.request,
        )
    except (
        NoAuthorizedToolError,
        ToolPermissionDeniedError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        ) from exc
    except (
        ToolCallingProviderError,
        InvalidToolCallingProviderResponseError,
        UnknownToolError,
        InvalidToolArgumentsError,
        ToolExecutionError,
        PersistenceUnavailableError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent service unavailable",
        ) from exc

    return AgentRunResponse(
        status=result.status,
        approval_id=result.approval_id,
        answer=result.answer,
        tool_used=result.tool_used,
        tool_status=result.tool_status,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
