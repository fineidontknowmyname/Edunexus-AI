from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables / .env file.
    Decorated with LRU cache via get_settings() to ensure the .env file
    is read only once for the lifetime of the process.
    """

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./edunexus.db"

    # ── LLM / AI ────────────────────────────────────────────────────────────
    groq_api_key: str = ""
    llm_provider: str = "groq"               # "groq" | "ollama"
    ollama_base_url: str = "http://localhost:11434"

    groq_primary_model: str = "llama3-70b-8192"
    groq_secondary_model: str = "llama3-8b-8192"
    embedding_model: str = "nomic-embed-text"

    # ── JWT / Auth ───────────────────────────────────────────────────────────
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 24

    # ── Runtime ─────────────────────────────────────────────────────────────
    environment: str = "development"         # "development" | "production"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached singleton of Settings.
    The LRU cache ensures the .env file is parsed only once,
    regardless of how many times this function is called.
    """
    return Settings()
