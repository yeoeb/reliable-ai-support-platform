from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import InvalidCredentialsError
from app.services.auth import authenticate_user


def test_authenticate_user_returns_user_when_credentials_are_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        email="alice@example.com",
        is_active=True,
    )

    credential = SimpleNamespace(
        user_id=user.id,
        password_hash="stored-password-hash",
    )

    monkeypatch.setattr(
        "app.services.auth.UserRepository.get_by_email",
        lambda self, email: user,
    )

    monkeypatch.setattr(
        "app.services.auth.get_user_credential_by_user_id",
        lambda session, user_id: credential,
    )

    monkeypatch.setattr(
        "app.services.auth.verify_password",
        lambda password, password_hash: True,
    )

    result = authenticate_user(
        object(),
        email="alice@example.com",
        password="correct-password",
    )

    assert result is user


def test_authenticate_user_rejects_unknown_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.auth.UserRepository.get_by_email",
        lambda self, email: None,
    )

    with pytest.raises(InvalidCredentialsError):
        authenticate_user(
            object(),
            email="missing@example.com",
            password="some-password",
        )


def test_authenticate_user_rejects_missing_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        email="alice@example.com",
        is_active=True,
    )

    monkeypatch.setattr(
        "app.services.auth.UserRepository.get_by_email",
        lambda self, email: user,
    )

    monkeypatch.setattr(
        "app.services.auth.get_user_credential_by_user_id",
        lambda session, user_id: None,
    )

    with pytest.raises(InvalidCredentialsError):
        authenticate_user(
            object(),
            email="alice@example.com",
            password="some-password",
        )


def test_authenticate_user_rejects_wrong_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        email="alice@example.com",
        is_active=True,
    )

    credential = SimpleNamespace(
        user_id=user.id,
        password_hash="stored-password-hash",
    )

    monkeypatch.setattr(
        "app.services.auth.UserRepository.get_by_email",
        lambda self, email: user,
    )

    monkeypatch.setattr(
        "app.services.auth.get_user_credential_by_user_id",
        lambda session, user_id: credential,
    )

    monkeypatch.setattr(
        "app.services.auth.verify_password",
        lambda password, password_hash: False,
    )

    with pytest.raises(InvalidCredentialsError):
        authenticate_user(
            object(),
            email="alice@example.com",
            password="wrong-password",
        )


def test_authenticate_user_rejects_inactive_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        email="alice@example.com",
        is_active=False,
    )

    credential = SimpleNamespace(
        user_id=user.id,
        password_hash="stored-password-hash",
    )

    monkeypatch.setattr(
        "app.services.auth.UserRepository.get_by_email",
        lambda self, email: user,
    )

    monkeypatch.setattr(
        "app.services.auth.get_user_credential_by_user_id",
        lambda session, user_id: credential,
    )

    monkeypatch.setattr(
        "app.services.auth.verify_password",
        lambda password, password_hash: True,
    )

    with pytest.raises(InvalidCredentialsError):
        authenticate_user(
            object(),
            email="alice@example.com",
            password="correct-password",
        )