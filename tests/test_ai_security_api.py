from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.core.errors import UnknownToolError
from app.db.session import get_db
from app.main import app
from app.services.agent import AgentService


client = TestClient(app)


def _user():
    return SimpleNamespace(
        id=uuid4(),
        is_active=True,
    )


def _db():
    yield object()


def test_attack_triggered_agent_failure_is_generic_and_no_leak(
    monkeypatch,
) -> None:
    attack_prompt = "ATTACK_PROMPT_SECRET_018"
    private_provider_detail = "ATTACK_PROVIDER_SECRET_018"

    def fail(self, **kwargs):
        raise UnknownToolError(private_provider_detail)

    monkeypatch.setattr(AgentService, "run", fail)
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db

    try:
        response = client.post(
            "/agent/run",
            json={"request": attack_prompt},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Agent service unavailable"
    }
    assert attack_prompt not in response.text
    assert private_provider_detail not in response.text
