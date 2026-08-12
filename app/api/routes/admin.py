from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_permission
from app.core.errors import (
    PersistenceUnavailableError,
    RoleNotFoundError,
    UserNotFoundError,
)
from app.db.session import get_db
from app.models.user import User
from app.services.rbac import RBACService


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)


require_rbac_manage = require_permission("rbac:manage")


@router.put(
    "/users/{user_id}/roles/{role_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def assign_user_role(
    user_id: UUID,
    role_name: str,
    _current_user: Annotated[
        User,
        Depends(require_rbac_manage),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Response:
    service = RBACService(db)

    try:
        service.assign_role(
            user_id=user_id,
            role_name=role_name,
        )

    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from exc

    except RoleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        ) from exc

    except PersistenceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistence service unavailable",
        ) from exc

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )


@router.delete(
    "/users/{user_id}/roles/{role_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_user_role(
    user_id: UUID,
    role_name: str,
    _current_user: Annotated[
        User,
        Depends(require_rbac_manage),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> Response:
    service = RBACService(db)

    try:
        service.remove_role(
            user_id=user_id,
            role_name=role_name,
        )

    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from exc

    except RoleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        ) from exc

    except PersistenceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistence service unavailable",
        ) from exc

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )