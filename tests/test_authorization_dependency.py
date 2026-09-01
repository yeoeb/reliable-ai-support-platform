from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.dependencies import authorization
from app.services.audit import AuditService


def test_require_permission_returns_user_when_allowed(
    monkeypatch,
) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        is_active=True,
    )

    repository = MagicMock()
    repository.has_permission.return_value = True

    monkeypatch.setattr(
        authorization,
        "RBACRepository",
        lambda session: repository,
    )
    monkeypatch.setattr(
        AuditService,
        "record_best_effort",
        lambda *args, **kwargs: None,
    )

    dependency = authorization.require_permission(
        "users:read"
    )

    result = dependency(
        current_user=user,
        session=object(),
    )

    assert result is user

    repository.has_permission.assert_called_once_with(
        user.id,
        "users:read",
    )


def test_require_permission_rejects_user_without_permission(
    monkeypatch,
) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        is_active=True,
    )

    repository = MagicMock()
    repository.has_permission.return_value = False

    monkeypatch.setattr(
        authorization,
        "RBACRepository",
        lambda session: repository,
    )

    dependency = authorization.require_permission(
        "rbac:manage"
    )

    with pytest.raises(HTTPException) as exc_info:
        dependency(
            current_user=user,
            session=object(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Forbidden"

    repository.has_permission.assert_called_once_with(
        user.id,
        "rbac:manage",
    )
