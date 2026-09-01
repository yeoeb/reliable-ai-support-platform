from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.dependencies import auth, authorization
from app.core.errors import InvalidCredentialsError, PersistenceUnavailableError
from app.main import app
from app.services.audit import AuditService
from app.services.rbac import RBACService


client = TestClient(app)


def test_failed_login_records_only_generic_metadata(monkeypatch) -> None:
    records: list[dict] = []

    monkeypatch.setattr(
        "app.api.routes.auth.authenticate_user",
        lambda *args, **kwargs: (_ for _ in ()).throw(InvalidCredentialsError()),
    )
    monkeypatch.setattr(
        AuditService,
        "record_best_effort",
        lambda self, **kwargs: records.append(kwargs),
    )

    response = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "secret-password"},
    )

    assert response.status_code == 401
    assert records == [{
        "actor_user_id": None,
        "action": "auth.login",
        "target_type": "authentication",
        "target_id": None,
        "outcome": "failure",
        "event_metadata": {"reason": "invalid_credentials"},
    }]
    assert "secret-password" not in str(records)
    assert "alice@example.com" not in str(records)


def test_invalid_token_audit_failure_preserves_401(monkeypatch) -> None:
    monkeypatch.setattr(
        auth,
        "decode_access_token",
        lambda token: (_ for _ in ()).throw(jwt.InvalidTokenError()),
    )
    monkeypatch.setattr(
        AuditService,
        "record_best_effort",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(
            credentials=SimpleNamespace(credentials="untrusted-token"),
            session=object(),
        )

    assert exc_info.value.status_code == 401


def test_permission_denial_audit_failure_preserves_403(monkeypatch) -> None:
    user = SimpleNamespace(id=uuid4(), is_active=True)
    repository = MagicMock()
    repository.has_permission.return_value = False
    monkeypatch.setattr(authorization, "RBACRepository", lambda session: repository)
    monkeypatch.setattr(AuditService, "record_best_effort", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        authorization.require_permission("rbac:manage")(
            current_user=user,
            session=object(),
        )

    assert exc_info.value.status_code == 403


def test_rbac_audit_failure_rolls_back_role_mutation() -> None:
    session = MagicMock()
    service = RBACService(session)
    user = SimpleNamespace(id=uuid4())
    role = SimpleNamespace(id=uuid4(), name="admin")
    service.user_repository.get_by_id = MagicMock(return_value=user)
    service.rbac_repository.get_role_by_name = MagicMock(return_value=role)
    service.rbac_repository.assign_role = MagicMock(return_value=True)
    service.audit_service.record = MagicMock(
        side_effect=OperationalError("insert", {}, Exception())
    )

    with pytest.raises(PersistenceUnavailableError):
        service.assign_role(
            actor_user_id=uuid4(),
            user_id=user.id,
            role_name=role.name,
        )

    session.commit.assert_not_called()
    session.rollback.assert_called_once()
