from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    database_url: str = "sqlite:///./edunexus.db"

    groq_api_key: str = ""
    llm_provider: str = "groq"
    ollama_base_url: str = "http://localhost:11434"

    groq_primary_model: str = "llama3-70b-8192"
    groq_secondary_model: str = "llama3-8b-8192"
    embedding_model: str = "nomic-embed-text"

    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 24

    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
