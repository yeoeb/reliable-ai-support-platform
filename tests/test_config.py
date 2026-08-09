from app.core.config import Settings

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