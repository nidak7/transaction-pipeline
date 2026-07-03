from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Transaction Pipeline"
    app_version: str = "0.1.0"
    database_url: str = (
        "postgresql+psycopg://transaction:transaction@postgres:5432/"
        "transaction_pipeline"
    )
    redis_url: str = "redis://redis:6379/0"
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.1"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    llm_batch_size: int = 25
    llm_timeout_seconds: float = 30.0
    llm_retry_base_delay_seconds: float = 1.0
    log_level: str = "INFO"
    upload_dir: Path = Path("/tmp/transaction-pipeline/uploads")


@lru_cache
def get_settings() -> Settings:
    return Settings()
