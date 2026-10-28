from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

DEFAULT_JWT_SECRET = "change-me-in-production"
MIN_PRODUCTION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    database_url: str

    groq_api_key: str = ""
    llm_provider: str = "groq"
    ollama_base_url: str = "http://localhost:11434"

    groq_primary_model: str = "openai/gpt-oss-20b"
    groq_secondary_model: str = "openai/gpt-oss-120b"
    embedding_model: str = "all-MiniLM-L6-v2"

    youtube_api_key: str = ""

    jwt_secret: str = DEFAULT_JWT_SECRET
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    environment: str = "development"
    cors_origins: str = "http://localhost:3000"

    run_ingestion_in_process: bool = True
    ingestion_poll_interval_seconds: int = 300
    max_upload_mb: int = 20
    fastembed_cache_path: str = ""
    mastery_v2_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_cors_origins() -> list[str]:
    settings = get_settings()
    return [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]


def validate_production_settings(settings: Settings) -> None:
    if not settings.is_production:
        return
    problems = []
    if settings.jwt_secret == DEFAULT_JWT_SECRET or len(settings.jwt_secret) < MIN_PRODUCTION_SECRET_LENGTH:
        problems.append(
            f"JWT_SECRET must be set to a random value of at least {MIN_PRODUCTION_SECRET_LENGTH} characters"
        )
    if not settings.database_url.startswith("postgresql"):
        problems.append("DATABASE_URL must point at PostgreSQL with pgvector")
    if settings.llm_provider.lower() == "groq" and not settings.groq_api_key:
        problems.append("GROQ_API_KEY is required when LLM_PROVIDER is groq")
    if problems:
        raise RuntimeError("Refusing to start in production: " + "; ".join(problems) + ".")
