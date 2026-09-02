from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.core.errors import NoAuthorizedToolError
from app.db.session import get_db
from app.main import app
from app.services.agent import AgentRunResult, AgentService


client = TestClient(app)


def override_user():
    return SimpleNamespace(id=uuid4(), is_active=True)


def override_db():
    yield object()


def payload():
    return {"request": "Check platform readiness."}


def test_agent_route_requires_authentication() -> None:
    response = client.post(
        "/agent/run",
        json=payload(),
    )
    assert response.status_code == 401


def test_agent_route_returns_bounded_metadata(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        AgentService,
        "run",
        lambda self, **kwargs: AgentRunResult(
            answer="Ready.",
            tool_used="platform_readiness",
            tool_status="ready",
            model="gpt-5.6-terra",
            input_tokens=5,
            output_tokens=2,
        ),
    )
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post(
            "/agent/run",
            json=payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Ready.",
        "tool_used": "platform_readiness",
        "tool_status": "ready",
        "model": "gpt-5.6-terra",
        "input_tokens": 5,
        "output_tokens": 2,
    }


def test_no_authorized_tool_maps_to_generic_403(
    monkeypatch,
) -> None:
    def deny(self, **kwargs):
        raise NoAuthorizedToolError("private detail")

    monkeypatch.setattr(AgentService, "run", deny)
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post(
            "/agent/run",
            json=payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}
    assert "private detail" not in response.text
