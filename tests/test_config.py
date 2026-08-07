import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_settings_accept_valid_values() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="support_platform_test",
        postgres_user="test_user",
        postgres_password="test-password",
    )

    assert settings.app_env == "test"
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432
    assert isinstance(settings.postgres_port, int)
    assert settings.postgres_db == "support_platform_test"
    assert settings.postgres_user == "test_user"
def test_settings_reject_missing_required_value(monkeypatch) -> None:
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            postgres_host="localhost",
            postgres_port=5432,
            postgres_db="support_platform_test",
            postgres_user="test_user",
        )
def test_settings_reject_invalid_postgres_port() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            postgres_host="localhost",
            postgres_port="not-a-port",
            postgres_db="support_platform_test",
            postgres_user="test_user",
            postgres_password="test-password",
        )
def test_database_url_and_safe_database_url() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="support_platform_test",
        postgres_user="test_user",
        postgres_password="test-password",
    )

    assert settings.database_url == (
        "postgresql+psycopg://"
        "test_user:test-password"
        "@localhost:5432/"
        "support_platform_test"
    )

    assert settings.safe_database_url == (
        "postgresql+psycopg://"
        "test_user:********"
        "@localhost:5432/"
        "support_platform_test"
    )

    assert "test-password" not in settings.safe_database_url