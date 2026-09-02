from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_permission
from app.core.errors import (
    ApprovalNotFoundError,
    ApprovalPermissionDeniedError,
    ApprovalStateConflictError,
    PersistenceUnavailableError,
    ToolExecutionError,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.approval import ApprovalRead
from app.services.approval import ApprovalService
from app.tools.system import build_default_tool_registry


router = APIRouter(
    prefix="/approvals",
    tags=["approvals"],
)

require_approval_decide = require_permission(
    "approval:decide"
)


def _service(db: Session) -> ApprovalService:
    return ApprovalService(
        db,
        build_default_tool_registry(),
    )


def _translate(
    exc: Exception,
) -> HTTPException:
    if isinstance(
        exc,
        ApprovalNotFoundError,
    ):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found",
        )
    if isinstance(
        exc,
        ApprovalPermissionDeniedError,
    ):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    if isinstance(
        exc,
        ApprovalStateConflictError,
    ):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approval is not pending or executable",
        )
    if isinstance(
        exc,
        (
            PersistenceUnavailableError,
            ToolExecutionError,
        ),
    ):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Approval service unavailable",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Approval service unavailable",
    )


@router.get(
    "/{approval_id}",
    response_model=ApprovalRead,
)
def get_approval(
    approval_id: UUID,
    current_user: Annotated[
        User,
        Depends(require_approval_decide),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> ApprovalRead:
    del current_user
    try:
        return ApprovalRead.model_validate(
            _service(db).get(
                approval_id=approval_id,
            )
        )
    except (
        ApprovalNotFoundError,
        PersistenceUnavailableError,
    ) as exc:
        raise _translate(exc) from exc


@router.post(
    "/{approval_id}/approve",
    response_model=ApprovalRead,
)
def approve(
    approval_id: UUID,
    current_user: Annotated[
        User,
        Depends(require_approval_decide),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> ApprovalRead:
    try:
        snapshot = _service(db).approve(
            approval_id=approval_id,
            approver_user_id=current_user.id,
        )
    except (
        ApprovalNotFoundError,
        ApprovalPermissionDeniedError,
        ApprovalStateConflictError,
        PersistenceUnavailableError,
        ToolExecutionError,
    ) as exc:
        raise _translate(exc) from exc
    return ApprovalRead.model_validate(snapshot)


@router.post(
    "/{approval_id}/reject",
    response_model=ApprovalRead,
)
def reject(
    approval_id: UUID,
    current_user: Annotated[
        User,
        Depends(require_approval_decide),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> ApprovalRead:
    try:
        snapshot = _service(db).reject(
            approval_id=approval_id,
            approver_user_id=current_user.id,
        )
    except (
        ApprovalNotFoundError,
        ApprovalPermissionDeniedError,
        ApprovalStateConflictError,
        PersistenceUnavailableError,
    ) as exc:
        raise _translate(exc) from exc
    return ApprovalRead.model_validate(snapshot)
