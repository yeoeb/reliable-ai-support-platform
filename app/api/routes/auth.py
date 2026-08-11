from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import InvalidCredentialsError
from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.auth import authenticate_user
from typing import Annotated

from app.api.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.user import UserRead

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def login(
    payload: LoginRequest,
    session: Session = Depends(get_db),
) -> TokenResponse:
    try:
        user = authenticate_user(
            session,
            email=str(payload.email),
            password=payload.password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    access_token = create_access_token(user.id)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )

@router.get(
    "/me",
    response_model=UserRead,
)
def get_me(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> User:
    return current_user