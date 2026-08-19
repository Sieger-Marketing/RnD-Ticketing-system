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

    #: Additional browser origins allowed to call the API, comma separated.
    #: The deployed frontend lives on a different origin from this API, and a
    #: hosting provider may serve it from more than one (a production domain
    #: plus per-branch preview domains), so the list has to be configurable
    #: without a code change.
    EXTRA_CORS_ORIGINS: str = ""

    #: Regex matching further allowed origins. Preview deployments get a
    #: generated subdomain per build, which no fixed list can enumerate.
    CORS_ORIGIN_REGEX: str = ""

    # Seeding
    SEED_DEFAULT_PASSWORD: str = "Design@123"

    # The one account that holds every permission. Created on bootstrap if it
    # does not exist; never modified afterwards. Blank the email to skip it.
    ADMIN_EMAIL: str = "admin@sieger.in"
    ADMIN_NAME: str = "Sieger Administrator"

    def assert_deployable(self) -> None:
        """Refuse to start a production deployment on development defaults.

        Every default in this class is chosen for a laptop. On a deployed
        service each one is a different kind of wrong, and each fails somewhere
        far from the cause: an unset DATABASE_URL surfaces sixty frames deep in
        SQLAlchemy as "connection to 127.0.0.1 refused", which reads like the
        database is down rather than never configured. Failing here, by name,
        costs one line of logs instead of a stack trace.
        """
        if self.ENVIRONMENT != "production":
            return

        problems: list[str] = []

        # A local database is a legitimate production choice when the API runs
        # on the same machine as Postgres, so the test is "never configured",
        # not "points at localhost". Only the untouched class default -- the
        # value a fresh clone gets -- means nobody set it.
        if self.DATABASE_URL == type(self).model_fields["DATABASE_URL"].default:
            problems.append(
                "DATABASE_URL is still the development default, so it was "
                "never set. Set it explicitly -- even when the database is on "
                "this same machine -- with the scheme written as "
                "postgresql+psycopg://, because this app uses psycopg 3 and "
                "will not load psycopg2."
            )
        if self.SECRET_KEY.startswith("dev-only"):
            problems.append("SECRET_KEY is still the development placeholder.")
        if self.JWT_SECRET.startswith("dev-only"):
            problems.append("JWT_SECRET is still the development placeholder.")
        if self.SEED_DEFAULT_PASSWORD == "Design@123":
            problems.append(
                "SEED_DEFAULT_PASSWORD is still the published default, which "
                "would give every seeded account -- including a Design Manager "
                "-- a password anyone reading this repository knows."
            )
        if "localhost" in self.FRONTEND_URL:
            problems.append(
                "FRONTEND_URL still points at localhost, so CORS will reject "
                "every request from the deployed site."
            )

        if problems:
            raise RuntimeError(
                "Refusing to start: this is configured as production but is "
                "running on development defaults.\n  - "
                + "\n  - ".join(problems)
            )

    @property
    def cors_origins(self) -> list[str]:
        origins = [
            self.FRONTEND_URL,
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
        ]
        origins += [
            origin.strip().rstrip("/")
            for origin in self.EXTRA_CORS_ORIGINS.split(",")
            if origin.strip()
        ]
        # A trailing slash makes an origin match nothing: the browser sends
        # "https://site.app", never "https://site.app/", and the comparison is
        # exact. Normalising here saves a failure that only shows up in a
        # browser console and never in curl.
        seen: dict[str, None] = {}
        for origin in origins:
            seen.setdefault(origin.rstrip("/"), None)
        return list(seen)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
