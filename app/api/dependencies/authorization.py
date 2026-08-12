import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.rbac import RBACRepository


logger = logging.getLogger(__name__)


def require_permission(
    permission_name: str,
) -> Callable[..., User]:
    def dependency(
        current_user: Annotated[
            User,
            Depends(get_current_user),
        ],
        session: Annotated[
            Session,
            Depends(get_db),
        ],
    ) -> User:
        repository = RBACRepository(session)

        if not repository.has_permission(
            current_user.id,
            permission_name,
        ):
            logger.info(
                "event=authorization.denied "
                "user_id=%s permission=%s",
                current_user.id,
                permission_name,
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )

        return current_user

    return dependency