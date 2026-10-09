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
    # Model time per turn, seconds. Past it the agent says a prepared line.
    voice_turn_budget_s: float = 7.0
    chat_turn_budget_s: float = 25.0
    # A manager's accepted handoff silences the agent in that dialog. After this
    # many hours without the handoff being resolved the agent answers again.
    # 0 = stay silent until a manager resolves it.
    manager_pause_hours: float = 24.0
    # Below this speech-recognition confidence a turn goes to the big model.
    stt_low_confidence: float = 0.6
    app_name: str = "Plumo"
    # gemini-2.5-flash and -lite are retired on 2026-10-20 (OpenRouter catalog,
    # checked 2026-10-09). Model ids come from env; fallbacks take over on 404.
    openrouter_small_model: str = "google/gemini-3.1-flash-lite"
    openrouter_big_model: str = "google/gemini-3.8-flash"
    openrouter_fallback_models: str = "google/gemini-3.7-flash,google/gemini-3.1-flash-lite"
    openrouter_base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    # Google AI Studio, OpenAI-compatible endpoint. Key: GEMINI_API_KEY.
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    gemini_small_model: str = "gemini-3.1-flash-lite"
    gemini_big_model: str = "gemini-3.8-flash"
    gemini_fallback_models: str = "gemini-3.7-flash,gemini-3.1-flash-lite"
    # Thinking is billed as output and delays a spoken reply. Empty = automatic:
    # "none" for 2.5 Flash, "minimal" for Gemini 3 (it cannot be switched off there).
    llm_reasoning_effort: str = ""
    # Retries on 429/5xx/network per model call, inside the turn budget.
    llm_max_retries: int = 2
    # Claude through the Anthropic SDK. Key: ANTHROPIC_API_KEY (or an `ant auth login` profile).
    anthropic_small_model: str = "claude-haiku-5-5"
    anthropic_big_model: str = "claude-sonnet-5-5"
    anthropic_effort: str = "low"
    # Self-hosted OpenAI-compatible server for the fine-tuned small model.
    # Ollama: http://127.0.0.1:11434/v1/chat/completions, vLLM: http://host:8000/v1/chat/completions.
    # Key LOCAL_LLM_API_KEY is optional. Tokens are counted, cost is 0.
    local_llm_base_url: str = "http://127.0.0.1:11434/v1/chat/completions"
    local_small_model: str = "plumo-small"
    local_big_model: str = "plumo-small"
    local_llm_timeout_s: float = 20.0
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
    def small_model_enabled(self) -> bool:
        """No small model yet (the local one is planned): its turns go to the big one."""

        name = self.small_model_provider.strip().lower()
        return self.mock_mode or name not in ("", "none", "off", "big", "mock")

    @property
    def mock_mode(self) -> bool:
        return self.ai_mode.strip().lower() == "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
