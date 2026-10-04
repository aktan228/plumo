"""Runtime settings. AI keys are intentionally absent."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed configuration.

    Real provider credentials belong in a future adapter, not here, until
    that adapter is added. The core only needs to know *which* adapter name
    to resolve.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://plumo:plumo@localhost:5432/plumo"
    ai_mode: str = "mock"
    small_model_provider: str = "mock"
    big_model_provider: str = "mock"
    stt_provider: str = "mock"
    tts_provider: str = "mock"
    language_detector: str = "mock"
    handoff_provider: str = "mock"
    router: str = "rules"
    default_language: str = "ru"
    default_business_id: str | None = None
    log_level: str = "INFO"
    small_model_confidence_threshold: float = 0.7
    app_name: str = "Plumo"

    @property
    def mock_mode(self) -> bool:
        return self.ai_mode.strip().lower() == "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
