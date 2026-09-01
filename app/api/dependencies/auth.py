import logging
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import get_by_id
from app.services.audit import AuditService


logger = logging.getLogger(__name__)


bearer_scheme = HTTPBearer(
    bearerFormat="JWT",
    auto_error=False,
)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: Annotated[
        Session,
        Depends(get_db),
    ],
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(
            credentials.credentials
        )

        user_id = UUID(payload["sub"])

    except (
        jwt.InvalidTokenError,
        ValueError,
        TypeError,
    ):
        logger.info("event=auth.token.invalid")
        AuditService(session).record_best_effort(
            actor_user_id=None,
            action="auth.token.invalid",
            target_type="authentication",
            target_id=None,
            outcome="failure",
            event_metadata={"reason": "invalid_token"},
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = get_by_id(
        session,
        user_id,
    )

    if user is None:
        AuditService(session).record_best_effort(
            actor_user_id=user_id,
            action="auth.user.invalid",
            target_type="user",
            target_id=str(user_id),
            outcome="failure",
            event_metadata={"reason": "user_not_found"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        AuditService(session).record_best_effort(
            actor_user_id=user_id,
            action="auth.user.invalid",
            target_type="user",
            target_id=str(user_id),
            outcome="failure",
            event_metadata={"reason": "user_inactive"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user
