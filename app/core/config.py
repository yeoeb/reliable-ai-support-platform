from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str

    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        password = self.postgres_password.get_secret_value()

        return (
            f"postgresql+psycopg://"
            f"{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}"
            f"/{self.postgres_db}"
        )
    @property
    def safe_database_url(self) -> str:
        return (
        f"postgresql+psycopg://"
        f"{self.postgres_user}:********"
        f"@{self.postgres_host}:{self.postgres_port}"
        f"/{self.postgres_db}"
    )