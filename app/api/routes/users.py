from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.errors import (
    PersistenceUnavailableError,
    UserAlreadyExistsError,
)
from app.db.session import get_db
from app.schemas.user import UserCreate, UserRead
from app.services.user import UserService

from app.api.dependencies.authorization import require_permission
from app.models.user import User

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
) -> UserRead:
    service = UserService(db)

    try:
        return service.create_user(data)

    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        ) from exc

    except PersistenceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistence service unavailable",
        ) from exc

@router.get(
    "",
    response_model=list[UserRead],
    status_code=status.HTTP_200_OK,
)
def list_users(
    db: Session = Depends(get_db),
    _current_user: User = Depends(
        require_permission("users:read")
    ),
) -> list[UserRead]:
    service = UserService(db)

    try:
        return service.list_users()

    except PersistenceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistence service unavailable",
        ) from exc