from app.core.config import Settings


def make_settings(**overrides) -> Settings:
    data = {
        "app_env": "development",
        "postgres_host": "localhost",
        "postgres_port": 5432,
        "postgres_db": "support_platform_test",
        "postgres_user": "test_user",
        "postgres_password": "test-password",
        "jwt_secret_key": "test-jwt-secret",
        "jwt_algorithm": "HS256",
        "access_token_expire_minutes": 30,
    }

    data.update(overrides)

    return Settings(**data)


def test_database_url_and_safe_database_url() -> None:
    settings = make_settings()

    database_url = settings.database_url

    assert database_url.drivername == "postgresql+psycopg"
    assert database_url.username == "test_user"
    assert database_url.password == "test-password"
    assert database_url.host == "localhost"
    assert database_url.port == 5432
    assert database_url.database == "support_platform_test"

    assert str(database_url) == (
        "postgresql+psycopg://"
        "test_user:***"
        "@localhost:5432/"
        "support_platform_test"
    )

    assert database_url.render_as_string(hide_password=False) == (
        "postgresql+psycopg://"
        "test_user:test-password"
        "@localhost:5432/"
        "support_platform_test"
    )


def test_settings_accept_jwt_configuration() -> None:
    settings = make_settings(
        jwt_secret_key="test-secret",
        jwt_algorithm="HS256",
        access_token_expire_minutes=30,
    )

    assert settings.jwt_algorithm == "HS256"
    assert settings.access_token_expire_minutes == 30


def test_jwt_secret_is_secret_type() -> None:
    settings = make_settings(
        jwt_secret_key="super-secret-value",
    )

    assert (
        settings.jwt_secret_key.get_secret_value()
        == "super-secret-value"
    )

    assert "super-secret-value" not in repr(
        settings.jwt_secret_key
    )