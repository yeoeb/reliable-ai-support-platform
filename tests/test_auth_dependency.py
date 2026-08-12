from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import auth


def make_credentials(
    token: str = "test-token",
) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )


def test_get_current_user_returns_user(
    monkeypatch,
):
    user_id = uuid4()

    user = SimpleNamespace(
        id=user_id,
        is_active=True,
    )

    monkeypatch.setattr(
        auth,
        "decode_access_token",
        lambda token: {"sub": str(user_id)},
    )

    monkeypatch.setattr(
        auth,
        "get_by_id",
        lambda session, user_id: user,
    )

    result = auth.get_current_user(
        credentials=make_credentials(),
        session=object(),
    )

    assert result is user


def test_get_current_user_rejects_missing_token():
    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(
            credentials=None,
            session=object(),
        )

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_invalid_token(
    monkeypatch,
):
    def raise_invalid_token(token):
        raise jwt.InvalidTokenError()

    monkeypatch.setattr(
        auth,
        "decode_access_token",
        raise_invalid_token,
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(
            credentials=make_credentials(),
            session=object(),
        )

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_invalid_subject(
    monkeypatch,
):
    monkeypatch.setattr(
        auth,
        "decode_access_token",
        lambda token: {"sub": "not-a-uuid"},
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(
            credentials=make_credentials(),
            session=object(),
        )

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_unknown_user(
    monkeypatch,
):
    user_id = uuid4()

    monkeypatch.setattr(
        auth,
        "decode_access_token",
        lambda token: {"sub": str(user_id)},
    )

    monkeypatch.setattr(
        auth,
        "get_by_id",
        lambda session, user_id: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(
            credentials=make_credentials(),
            session=object(),
        )

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_inactive_user(
    monkeypatch,
):
    user_id = uuid4()

    user = SimpleNamespace(
        id=user_id,
        is_active=False,
    )

    monkeypatch.setattr(
        auth,
        "decode_access_token",
        lambda token: {"sub": str(user_id)},
    )

    monkeypatch.setattr(
        auth,
        "get_by_id",
        lambda session, user_id: user,
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(
            credentials=make_credentials(),
            session=object(),
        )

    assert exc_info.value.status_code == 403