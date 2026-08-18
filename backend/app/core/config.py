"""Application configuration.

Every tunable is an environment variable with a development-safe default, so a
fresh clone runs after `cp .env.example .env`. Nothing here is secret by
default; secrets must come from the environment.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    PROJECT_NAME: str = "Design Operations Management System"
    API_V1_PREFIX: str = "/api"
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = (
        "postgresql+psycopg://designops:designops@127.0.0.1:5432/designops"
    )
    SQL_ECHO: bool = False

    # Auth
    SECRET_KEY: str = "dev-only-secret-change-me"
    JWT_SECRET: str = "dev-only-jwt-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    # Storage
    FILE_STORAGE_PROVIDER: str = "local"
    FILE_STORAGE_PATH: str = "../storage"
    MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024

    # Email
    EMAIL_PROVIDER: str = "console"
    EMAIL_API_KEY: str = ""
    EMAIL_FROM: str = "designops@example.com"

    # URLs
    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_URL: str = "http://localhost:8000"

    # Seeding
    SEED_DEFAULT_PASSWORD: str = "Design@123"

    @property
    def cors_origins(self) -> list[str]:
        return [
            self.FRONTEND_URL,
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
