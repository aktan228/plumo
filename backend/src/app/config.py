"""Runtime settings. AI keys are intentionally absent."""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """Environment-backed configuration.

    Adapter names live here. The OpenRouter secret is read by
    OpenRouterLLMProvider from OPENROUTER_API_KEY, not logged.
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
    openrouter_small_model: str = "google/gemini-2.5-flash"
    openrouter_big_model: str = "google/gemini-2.5-flash"
    openrouter_base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    # Google AI Studio, OpenAI-compatible endpoint. Key: GEMINI_API_KEY.
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    gemini_small_model: str = "gemini-2.5-flash-lite"
    gemini_big_model: str = "gemini-2.5-flash"
    # Any other OpenAI-compatible vendor. Key: LLM_API_KEY.
    llm_base_url: str = "https://api.deepseek.com/chat/completions"
    llm_small_model: str = "deepseek-chat"
    llm_big_model: str = "deepseek-chat"
    # Voice platform behind the phone number. Its secrets are read from
    # ELEVENLABS_LLM_TOKEN and ELEVENLABS_WEBHOOK_SECRET, not stored here.
    voice_platform: str = "elevenlabs"
    # Platform price per call minute, from the ElevenLabs plan. 0 = unknown.
    voice_usd_per_minute: float = 0.0
    # Comma-separated origins allowed to call the API from a browser (dashboard).
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def mock_mode(self) -> bool:
        return self.ai_mode.strip().lower() == "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
