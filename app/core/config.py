from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    app_env: str

    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr

    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    log_level: str = "INFO"

    openai_api_key: SecretStr | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 32
    knowledge_chunk_size: int = 1000
    knowledge_chunk_overlap: int = 150

    rag_model: str = "gpt-5.6-terra"
    rag_max_output_tokens: int = 1200

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {
            "CRITICAL",
            "ERROR",
            "WARNING",
            "INFO",
            "DEBUG",
        }

        if normalized not in allowed:
            raise ValueError(
                "LOG_LEVEL must be one of "
                "CRITICAL, ERROR, WARNING, INFO, DEBUG"
            )

        return normalized

    @field_validator("embedding_model")
    @classmethod
    def validate_embedding_model(cls, value: str) -> str:
        normalized = value.strip()

        if normalized != "text-embedding-3-small":
            raise ValueError(
                "EMBEDDING_MODEL must be "
                "text-embedding-3-small for Issue #012"
            )

        return normalized

    @field_validator("embedding_dimensions")
    @classmethod
    def validate_embedding_dimensions(cls, value: int) -> int:
        if value != 1536:
            raise ValueError(
                "EMBEDDING_DIMENSIONS must be 1536 "
                "for Issue #012"
            )

        return value

    @field_validator("embedding_batch_size")
    @classmethod
    def validate_embedding_batch_size(cls, value: int) -> int:
        if not 1 <= value <= 32:
            raise ValueError(
                "EMBEDDING_BATCH_SIZE must be between 1 and 32"
            )

        return value

    @field_validator("knowledge_chunk_size")
    @classmethod
    def validate_knowledge_chunk_size(cls, value: int) -> int:
        if not 1 <= value <= 2000:
            raise ValueError(
                "KNOWLEDGE_CHUNK_SIZE must be between 1 and 2000"
            )

        return value

    @field_validator("knowledge_chunk_overlap")
    @classmethod
    def validate_knowledge_chunk_overlap_non_negative(
        cls,
        value: int,
    ) -> int:
        if value < 0:
            raise ValueError(
                "KNOWLEDGE_CHUNK_OVERLAP must be non-negative"
            )

        return value

    @model_validator(mode="after")
    def validate_embedding_pipeline_settings(self) -> "Settings":
        if self.knowledge_chunk_overlap >= self.knowledge_chunk_size:
            raise ValueError(
                "KNOWLEDGE_CHUNK_OVERLAP must be smaller than "
                "KNOWLEDGE_CHUNK_SIZE"
            )

        return self

    @field_validator("rag_model")
    @classmethod
    def validate_rag_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(
                "RAG_MODEL must not be empty"
            )
        return normalized

    @field_validator("rag_max_output_tokens")
    @classmethod
    def validate_rag_max_output_tokens(cls, value: int) -> int:
        if not 128 <= value <= 8192:
            raise ValueError(
                "RAG_MAX_OUTPUT_TOKENS must be between 128 and 8192"
            )
        return value

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def safe_database_url(self) -> str:
        return self.database_url.render_as_string(hide_password=True)


settings = Settings()