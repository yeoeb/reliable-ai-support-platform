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


class FailingAuditSession:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure
        self.rollback = MagicMock()

    def add(self, event) -> None:
        pass

    def flush(self) -> None:
        raise self.failure

    def commit(self) -> None:
        raise self.failure


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
    serialized_records = str(records)
    for sensitive_value in (
        "secret-password",
        "alice@example.com",
        "password_hash",
        "jwt-secret",
        "arbitrary-request-body",
    ):
        assert sensitive_value not in serialized_records


def test_login_success_records_authenticated_user(monkeypatch) -> None:
    user = SimpleNamespace(id=uuid4(), is_active=True)
    records: list[dict] = []
    monkeypatch.setattr("app.api.routes.auth.authenticate_user", lambda *args, **kwargs: user)
    monkeypatch.setattr(
        AuditService,
        "record_best_effort",
        lambda self, **kwargs: records.append(kwargs),
    )

    response = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "secret-password"},
    )

    assert response.status_code == 200
    assert records == [{
        "actor_user_id": user.id,
        "action": "auth.login",
        "target_type": "user",
        "target_id": str(user.id),
        "outcome": "success",
        "event_metadata": {},
    }]


def test_invalid_token_audit_excludes_raw_token(monkeypatch) -> None:
    records: list[dict] = []
    raw_token = "sensitive-raw-access-token"

    monkeypatch.setattr(
        auth,
        "decode_access_token",
        lambda token: (_ for _ in ()).throw(jwt.InvalidTokenError()),
    )
    monkeypatch.setattr(
        AuditService,
        "record_best_effort",
        lambda self, **kwargs: records.append(kwargs),
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(
            credentials=SimpleNamespace(credentials=raw_token),
            session=object(),
        )

    assert exc_info.value.status_code == 401
    assert records == [{
        "actor_user_id": None,
        "action": "auth.token.invalid",
        "target_type": "authentication",
        "target_id": None,
        "outcome": "failure",
        "event_metadata": {"reason": "invalid_token"},
    }]
    serialized_records = str(records)
    assert raw_token not in serialized_records
    assert "Authorization" not in serialized_records
    assert "Bearer" not in serialized_records


def test_invalid_token_persistence_failure_preserves_401(monkeypatch) -> None:
    monkeypatch.setattr(
        auth,
        "decode_access_token",
        lambda token: (_ for _ in ()).throw(jwt.InvalidTokenError()),
    )
    session = FailingAuditSession(OperationalError("insert", {}, Exception()))

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(
            credentials=SimpleNamespace(credentials="untrusted-token"),
            session=session,
        )

    assert exc_info.value.status_code == 401
    session.rollback.assert_called_once()


def test_permission_denial_persistence_failure_preserves_403(monkeypatch) -> None:
    user = SimpleNamespace(id=uuid4(), is_active=True)
    repository = MagicMock()
    repository.has_permission.return_value = False
    monkeypatch.setattr(authorization, "RBACRepository", lambda session: repository)
    session = FailingAuditSession(OperationalError("insert", {}, Exception()))

    with pytest.raises(HTTPException) as exc_info:
        authorization.require_permission("rbac:manage")(
            current_user=user,
            session=session,
        )

    assert exc_info.value.status_code == 403
    session.rollback.assert_called_once()


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


def test_rbac_remove_audit_failure_rolls_back_role_mutation() -> None:
    session = MagicMock()
    service = RBACService(session)
    user = SimpleNamespace(id=uuid4())
    role = SimpleNamespace(id=uuid4(), name="admin")
    service.user_repository.get_by_id = MagicMock(return_value=user)
    service.rbac_repository.get_role_by_name = MagicMock(return_value=role)
    service.rbac_repository.remove_role = MagicMock(return_value=True)
    service.audit_service.record = MagicMock(
        side_effect=OperationalError("insert", {}, Exception())
    )

    with pytest.raises(PersistenceUnavailableError):
        service.remove_role(
            actor_user_id=uuid4(),
            user_id=user.id,
            role_name=role.name,
        )

    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_rbac_assign_records_actor_target_role_and_change() -> None:
    session = MagicMock()
    service = RBACService(session)
    actor_user_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    role = SimpleNamespace(id=uuid4(), name="admin")
    service.user_repository.get_by_id = MagicMock(return_value=user)
    service.rbac_repository.get_role_by_name = MagicMock(return_value=role)
    service.rbac_repository.assign_role = MagicMock(return_value=True)
    service.audit_service.record = MagicMock()

    service.assign_role(
        actor_user_id=actor_user_id,
        user_id=user.id,
        role_name=role.name,
    )

    service.audit_service.record.assert_called_once_with(
        actor_user_id=actor_user_id,
        action="rbac.role.assign",
        target_type="user",
        target_id=str(user.id),
        outcome="success",
        event_metadata={"role": "admin", "changed": True},
    )
    session.commit.assert_called_once()


def test_rbac_remove_records_actor_target_role_and_no_change() -> None:
    session = MagicMock()
    service = RBACService(session)
    actor_user_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    role = SimpleNamespace(id=uuid4(), name="admin")
    service.user_repository.get_by_id = MagicMock(return_value=user)
    service.rbac_repository.get_role_by_name = MagicMock(return_value=role)
    service.rbac_repository.remove_role = MagicMock(return_value=False)
    service.audit_service.record = MagicMock()

    service.remove_role(
        actor_user_id=actor_user_id,
        user_id=user.id,
        role_name=role.name,
    )

    service.audit_service.record.assert_called_once_with(
        actor_user_id=actor_user_id,
        action="rbac.role.remove",
        target_type="user",
        target_id=str(user.id),
        outcome="success",
        event_metadata={"role": "admin", "changed": False},
    )
    session.commit.assert_called_once()
