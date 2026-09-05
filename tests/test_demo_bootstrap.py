from __future__ import annotations

import importlib.util
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.errors import InvalidCredentialsError
from app.schemas.user import UserCreate
from app.services.demo_bootstrap import (
    DemoBootstrapService,
    DemoEnvironmentError,
    DemoKnowledgeSeed,
    ExistingUserPromotionRequiredError,
    LiveAIConfigurationError,
    load_demo_knowledge,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATOR = UserCreate(
    email="operator@example.com",
    display_name="Demo Operator",
    password="correct-demo-password",
)
SEEDS = (
    DemoKnowledgeSeed(
        title="One",
        source_name="demo/one.md",
        content="# One\nDeterministic content.",
    ),
)


def make_service(
    *,
    app_env: str = "development",
) -> tuple[DemoBootstrapService, MagicMock]:
    session = MagicMock(spec=Session)
    service = DemoBootstrapService(
        session,
        app_env=app_env,
    )
    service.user_repository = MagicMock()
    service.rbac_repository = MagicMock()
    service.user_service = MagicMock()
    service.rbac_service = MagicMock()
    service.knowledge_service = MagicMock()
    return service, session


def knowledge_result(*, changed: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        document=SimpleNamespace(id=uuid4()),
        changed=changed,
    )


@pytest.mark.parametrize("app_env", ["production", "staging", "test", ""])
def test_bootstrap_refuses_non_development_environment(
    app_env: str,
) -> None:
    service, session = make_service(app_env=app_env)

    with pytest.raises(DemoEnvironmentError):
        service.bootstrap(
            administrator=ADMINISTRATOR,
            knowledge_seeds=SEEDS,
        )

    service.user_repository.get_by_email.assert_not_called()
    session.commit.assert_not_called()


def test_new_administrator_uses_existing_user_and_rbac_services() -> None:
    service, _ = make_service()
    user = SimpleNamespace(id=uuid4())
    service.user_repository.get_by_email.return_value = None
    service.user_service.create_user.return_value = user
    service.knowledge_service.ingest.return_value = knowledge_result()

    result = service.bootstrap(
        administrator=ADMINISTRATOR,
        knowledge_seeds=SEEDS,
    )

    service.user_service.create_user.assert_called_once_with(ADMINISTRATOR)
    service.rbac_service.assign_role.assert_called_once_with(
        actor_user_id=user.id,
        user_id=user.id,
        role_name="admin",
    )
    assert result.administrator_created is True
    assert result.admin_role_changed is True


def test_user_service_hashes_new_administrator_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session = make_service()
    user = SimpleNamespace(id=uuid4())
    role = SimpleNamespace(id=uuid4())
    service.user_repository.get_by_email.return_value = None
    service.user_service = __import__(
        "app.services.user", fromlist=["UserService"]
    ).UserService(session)
    service.user_service.repository = MagicMock()
    service.user_service.credential_repository = MagicMock()
    service.user_service.rbac_repository = MagicMock()
    service.user_service.repository.create.return_value = user
    service.user_service.rbac_repository.get_role_by_name.return_value = role
    service.knowledge_service.ingest.return_value = knowledge_result()
    hash_password = MagicMock(return_value="argon2-password-hash")
    monkeypatch.setattr("app.services.user.hash_password", hash_password)

    service.bootstrap(
        administrator=ADMINISTRATOR,
        knowledge_seeds=SEEDS,
    )

    hash_password.assert_called_once_with("correct-demo-password")
    service.user_service.credential_repository.create.assert_called_once_with(
        user_id=user.id,
        password_hash="argon2-password-hash",
    )
    assert "correct-demo-password" not in str(
        service.user_service.credential_repository.create.call_args
    )


def test_existing_admin_must_authenticate_and_is_reused_idempotently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session = make_service()
    user = SimpleNamespace(id=uuid4())
    role = SimpleNamespace(id=uuid4())
    service.user_repository.get_by_email.return_value = user
    service.rbac_repository.get_role_by_name.return_value = role
    session.scalar.return_value = user.id
    service.knowledge_service.ingest.return_value = knowledge_result(
        changed=False
    )
    authenticate = MagicMock(return_value=user)
    monkeypatch.setattr(
        "app.services.demo_bootstrap.authenticate_user",
        authenticate,
    )

    result = service.bootstrap(
        administrator=ADMINISTRATOR,
        knowledge_seeds=SEEDS,
    )

    authenticate.assert_called_once_with(
        session,
        email="operator@example.com",
        password="correct-demo-password",
    )
    service.rbac_service.assign_role.assert_not_called()
    assert result.administrator_created is False
    assert result.admin_role_changed is False
    assert result.knowledge[0].changed is False


def test_wrong_existing_password_fails_before_role_or_knowledge_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session = make_service()
    service.user_repository.get_by_email.return_value = SimpleNamespace(
        id=uuid4()
    )
    monkeypatch.setattr(
        "app.services.demo_bootstrap.authenticate_user",
        MagicMock(side_effect=InvalidCredentialsError),
    )

    with pytest.raises(InvalidCredentialsError):
        service.bootstrap(
            administrator=ADMINISTRATOR,
            knowledge_seeds=SEEDS,
            promote_existing=True,
        )

    service.rbac_service.assign_role.assert_not_called()
    service.knowledge_service.ingest.assert_not_called()
    session.rollback.assert_called_once()


def test_existing_non_admin_refuses_without_explicit_promotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session = make_service()
    user = SimpleNamespace(id=uuid4())
    service.user_repository.get_by_email.return_value = user
    service.rbac_repository.get_role_by_name.return_value = SimpleNamespace(
        id=uuid4()
    )
    session.scalar.return_value = None
    monkeypatch.setattr(
        "app.services.demo_bootstrap.authenticate_user",
        MagicMock(return_value=user),
    )

    with pytest.raises(ExistingUserPromotionRequiredError):
        service.bootstrap(
            administrator=ADMINISTRATOR,
            knowledge_seeds=SEEDS,
        )

    service.rbac_service.assign_role.assert_not_called()
    service.knowledge_service.ingest.assert_not_called()


def test_explicit_existing_promotion_uses_authenticated_user_as_audit_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session = make_service()
    user = SimpleNamespace(id=uuid4())
    service.user_repository.get_by_email.return_value = user
    service.rbac_repository.get_role_by_name.return_value = SimpleNamespace(
        id=uuid4()
    )
    session.scalar.return_value = None
    service.knowledge_service.ingest.return_value = knowledge_result()
    monkeypatch.setattr(
        "app.services.demo_bootstrap.authenticate_user",
        MagicMock(return_value=user),
    )

    result = service.bootstrap(
        administrator=ADMINISTRATOR,
        knowledge_seeds=SEEDS,
        promote_existing=True,
    )

    service.rbac_service.assign_role.assert_called_once_with(
        actor_user_id=user.id,
        user_id=user.id,
        role_name="admin",
    )
    assert result.admin_role_changed is True


def test_demo_knowledge_files_are_fixed_and_deterministic() -> None:
    first = load_demo_knowledge(REPOSITORY_ROOT / "demo" / "knowledge")
    second = load_demo_knowledge(REPOSITORY_ROOT / "demo" / "knowledge")

    assert first == second
    assert [item.source_name for item in first] == [
        "demo/password-reset.md",
        "demo/vpn-access.md",
        "demo/escalation-policy.md",
    ]
    assert all(item.content.strip() for item in first)


def test_default_mode_never_constructs_or_calls_embedding_service() -> None:
    service, _ = make_service()
    user = SimpleNamespace(id=uuid4())
    service.user_repository.get_by_email.return_value = None
    service.user_service.create_user.return_value = user
    service.knowledge_service.ingest.return_value = knowledge_result()

    result = service.bootstrap(
        administrator=ADMINISTRATOR,
        knowledge_seeds=SEEDS,
    )

    assert service.embedding_service is None
    assert result.live_ai_enabled is False
    assert result.knowledge[0].embedded is False


def test_live_ai_missing_provider_refuses_before_database_work() -> None:
    service, session = make_service()

    with pytest.raises(LiveAIConfigurationError):
        service.bootstrap(
            administrator=ADMINISTRATOR,
            knowledge_seeds=SEEDS,
            enable_live_ai=True,
        )

    service.user_repository.get_by_email.assert_not_called()
    session.commit.assert_not_called()


def test_live_ai_embeds_each_seed_only_after_ingestion() -> None:
    service, _ = make_service()
    user = SimpleNamespace(id=uuid4())
    ingested = knowledge_result()
    service.user_repository.get_by_email.return_value = None
    service.user_service.create_user.return_value = user
    service.knowledge_service.ingest.return_value = ingested
    service.embedding_service = MagicMock()
    service.embedding_service.embed_document.return_value = SimpleNamespace(
        changed=True
    )

    result = service.bootstrap(
        administrator=ADMINISTRATOR,
        knowledge_seeds=SEEDS,
        enable_live_ai=True,
    )

    service.embedding_service.embed_document.assert_called_once_with(
        actor_user_id=user.id,
        document_id=ingested.document.id,
    )
    assert result.knowledge[0].embedded is True
    assert result.knowledge[0].embedding_changed is True


def test_injected_knowledge_failure_rolls_back_and_stops_embedding() -> None:
    service, session = make_service()
    user = SimpleNamespace(id=uuid4())
    service.user_repository.get_by_email.return_value = None
    service.user_service.create_user.return_value = user
    service.knowledge_service.ingest.side_effect = RuntimeError("injected")
    service.embedding_service = MagicMock()

    with pytest.raises(RuntimeError, match="injected"):
        service.bootstrap(
            administrator=ADMINISTRATOR,
            knowledge_seeds=SEEDS,
            enable_live_ai=True,
        )

    session.rollback.assert_called()
    service.embedding_service.embed_document.assert_not_called()


def _load_cli_module():
    path = REPOSITORY_ROOT / "scripts" / "bootstrap_demo.py"
    spec = importlib.util.spec_from_file_location("bootstrap_demo_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_has_no_password_or_token_argument() -> None:
    module = _load_cli_module()
    option_strings = {
        option
        for action in module.build_parser()._actions
        for option in action.option_strings
    }

    assert not any(
        "password" in option.lower() or "token" in option.lower()
        for option in option_strings
    )


def test_cli_output_never_contains_supplied_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_cli_module()
    secret = "never-print-this-password"
    result = SimpleNamespace(
        administrator_user_id=uuid4(),
        administrator_created=True,
        admin_role_changed=True,
        knowledge=(
            SimpleNamespace(changed=True, embedded=False),
        ),
        live_ai_enabled=False,
    )

    import app.db.session as db_session
    import app.services.demo_bootstrap as demo_bootstrap

    class FakeService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def bootstrap(self, **kwargs):
            return result

    monkeypatch.setattr(module.getpass, "getpass", lambda prompt: secret)
    monkeypatch.setattr(db_session, "SessionLocal", lambda: nullcontext(object()))
    monkeypatch.setattr(demo_bootstrap, "DemoBootstrapService", FakeService)

    exit_code = module.main(["--email", "operator@example.com"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert secret not in captured.out
    assert secret not in captured.err


def test_cli_environment_guard_runs_before_secret_prompt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_cli_module()
    from app.core.config import settings

    prompt = MagicMock(side_effect=AssertionError("must not prompt"))
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(module.getpass, "getpass", prompt)

    exit_code = module.main(["--email", "operator@example.com"])
    captured = capsys.readouterr()

    assert exit_code == 1
    prompt.assert_not_called()
    assert "only in development" in captured.err


def test_cli_missing_live_ai_key_runs_before_secret_prompt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_cli_module()
    from app.core.config import settings

    prompt = MagicMock(side_effect=AssertionError("must not prompt"))
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(module.getpass, "getpass", prompt)

    exit_code = module.main(
        ["--email", "operator@example.com", "--enable-live-ai"]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    prompt.assert_not_called()
    assert "OPENAI_API_KEY is not configured" in captured.err
