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


def test_log_level_defaults_to_info() -> None:
    settings = make_settings()

    assert settings.log_level == "INFO"


def test_log_level_is_normalized() -> None:
    settings = make_settings(
        log_level="debug",
    )

    assert settings.log_level == "DEBUG"


def test_invalid_log_level_is_rejected() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(
        ValidationError,
        match="LOG_LEVEL",
    ):
        make_settings(
            log_level="verbose",
        )



def test_embedding_settings_defaults() -> None:
    settings = make_settings()

    assert settings.openai_api_key is None
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimensions == 1536
    assert settings.embedding_batch_size == 32
    assert settings.knowledge_chunk_size == 1000
    assert settings.knowledge_chunk_overlap == 150


def test_openai_api_key_is_optional_secret() -> None:
    settings = make_settings(
        openai_api_key="test-openai-key",
    )

    assert (
        settings.openai_api_key is not None
        and settings.openai_api_key.get_secret_value()
        == "test-openai-key"
    )
    assert "test-openai-key" not in repr(
        settings.openai_api_key
    )


def test_embedding_batch_size_is_bounded() -> None:
    import pytest
    from pydantic import ValidationError

    for invalid in (0, 33):
        with pytest.raises(
            ValidationError,
            match="EMBEDDING_BATCH_SIZE",
        ):
            make_settings(
                embedding_batch_size=invalid,
            )


def test_embedding_dimensions_are_fixed_for_issue_012() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(
        ValidationError,
        match="EMBEDDING_DIMENSIONS",
    ):
        make_settings(
            embedding_dimensions=512,
        )


def test_embedding_model_is_fixed_for_issue_012() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(
        ValidationError,
        match="EMBEDDING_MODEL",
    ):
        make_settings(
            embedding_model="text-embedding-3-large",
        )


def test_knowledge_chunk_size_is_bounded() -> None:
    import pytest
    from pydantic import ValidationError

    for invalid in (0, 2001):
        with pytest.raises(
            ValidationError,
            match="KNOWLEDGE_CHUNK_SIZE",
        ):
            make_settings(
                knowledge_chunk_size=invalid,
            )


def test_knowledge_chunk_overlap_must_be_smaller_than_size() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(
        ValidationError,
        match="KNOWLEDGE_CHUNK_OVERLAP",
    ):
        make_settings(
            knowledge_chunk_size=100,
            knowledge_chunk_overlap=100,
        )


def test_knowledge_chunk_overlap_cannot_be_negative() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(
        ValidationError,
        match="KNOWLEDGE_CHUNK_OVERLAP",
    ):
        make_settings(
            knowledge_chunk_overlap=-1,
        )


def test_rag_settings_defaults() -> None:
    settings = make_settings()

    assert settings.rag_model == "gpt-5.6-terra"
    assert settings.rag_max_output_tokens == 1200


def test_rag_model_must_not_be_empty() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(
        ValidationError,
        match="RAG_MODEL",
    ):
        make_settings(
            rag_model="   ",
        )


def test_rag_output_tokens_are_bounded() -> None:
    import pytest
    from pydantic import ValidationError

    for invalid in (127, 8193):
        with pytest.raises(
            ValidationError,
            match="RAG_MAX_OUTPUT_TOKENS",
        ):
            make_settings(
                rag_max_output_tokens=invalid,
            )
