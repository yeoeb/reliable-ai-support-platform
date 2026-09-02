from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.routes.approvals import (
    require_approval_decide,
)
from app.core.errors import (
    ApprovalNotFoundError,
    ApprovalPermissionDeniedError,
    ApprovalStateConflictError,
    PersistenceUnavailableError,
)
from app.db.session import get_db
from app.main import app
from app.services.approval import (
    ApprovalService,
    ApprovalSnapshot,
)


client = TestClient(app)
NOW = datetime(
    2026,
    9,
    2,
    12,
    0,
    tzinfo=timezone.utc,
)


def override_decider():
    return SimpleNamespace(
        id=uuid4(),
        is_active=True,
    )


def override_db():
    yield object()


def snapshot(
    *,
    status="pending",
) -> ApprovalSnapshot:
    return ApprovalSnapshot(
        id=uuid4(),
        requested_by_user_id=uuid4(),
        tool_name="grant_support_agent_role",
        tool_arguments={
            "user_id": str(uuid4()),
        },
        status=status,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
        decided_by_user_id=None,
        decided_at=None,
        executed_at=None,
    )


def test_approval_routes_require_authentication() -> None:
    approval_id = uuid4()

    assert client.get(
        f"/approvals/{approval_id}"
    ).status_code == 401
    assert client.post(
        f"/approvals/{approval_id}/approve"
    ).status_code == 401
    assert client.post(
        f"/approvals/{approval_id}/reject"
    ).status_code == 401


def test_get_approval_returns_safe_exact_action(
    monkeypatch,
) -> None:
    expected = snapshot()
    monkeypatch.setattr(
        ApprovalService,
        "get",
        lambda self, **kwargs: expected,
    )
    app.dependency_overrides[
        require_approval_decide
    ] = override_decider
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.get(
            f"/approvals/{expected.id}"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_name"] == (
        "grant_support_agent_role"
    )
    assert set(
        payload["tool_arguments"]
    ) == {"user_id"}
    assert "role_name" not in payload[
        "tool_arguments"
    ]
    assert "provider" not in payload
    assert "model_request" not in payload


def test_approve_returns_executed_state(
    monkeypatch,
) -> None:
    expected = snapshot(
        status="executed"
    )
    expected = ApprovalSnapshot(
        **{
            **expected.__dict__,
            "decided_by_user_id": uuid4(),
            "decided_at": NOW,
            "executed_at": NOW,
        }
    )
    monkeypatch.setattr(
        ApprovalService,
        "approve",
        lambda self, **kwargs: expected,
    )
    app.dependency_overrides[
        require_approval_decide
    ] = override_decider
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            f"/approvals/{expected.id}/approve"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "executed"


def test_reject_returns_rejected_state(
    monkeypatch,
) -> None:
    expected = snapshot(
        status="rejected"
    )
    monkeypatch.setattr(
        ApprovalService,
        "reject",
        lambda self, **kwargs: expected,
    )
    app.dependency_overrides[
        require_approval_decide
    ] = override_decider
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            f"/approvals/{expected.id}/reject"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_approval_not_found_maps_to_generic_404(
    monkeypatch,
) -> None:
    def missing(self, **kwargs):
        raise ApprovalNotFoundError(
            "private database detail"
        )

    monkeypatch.setattr(
        ApprovalService,
        "get",
        missing,
    )
    app.dependency_overrides[
        require_approval_decide
    ] = override_decider
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.get(
            f"/approvals/{uuid4()}"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Approval not found"
    }
    assert "private database detail" not in response.text


def test_approval_conflict_maps_to_409(
    monkeypatch,
) -> None:
    def conflict(self, **kwargs):
        raise ApprovalStateConflictError

    monkeypatch.setattr(
        ApprovalService,
        "approve",
        conflict,
    )
    app.dependency_overrides[
        require_approval_decide
    ] = override_decider
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            f"/approvals/{uuid4()}/approve"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409


def test_service_permission_revocation_maps_to_403(
    monkeypatch,
) -> None:
    def denied(self, **kwargs):
        raise ApprovalPermissionDeniedError

    monkeypatch.setattr(
        ApprovalService,
        "approve",
        denied,
    )
    app.dependency_overrides[
        require_approval_decide
    ] = override_decider
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            f"/approvals/{uuid4()}/approve"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Forbidden"
    }


def test_persistence_failure_maps_to_generic_503(
    monkeypatch,
) -> None:
    def unavailable(self, **kwargs):
        raise PersistenceUnavailableError(
            "private SQL detail"
        )

    monkeypatch.setattr(
        ApprovalService,
        "approve",
        unavailable,
    )
    app.dependency_overrides[
        require_approval_decide
    ] = override_decider
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            f"/approvals/{uuid4()}/approve"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Approval service unavailable"
    }
    assert "private SQL detail" not in response.text
