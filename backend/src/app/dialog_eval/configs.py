"""Agent configurations the eval compares. Each one is a Settings override for the real core."""

from __future__ import annotations

from app.config import Settings

# OpenRouter model ids, checked against https://openrouter.ai/api/v1/models on 2026-10-24.
MODELS = {
    "haiku": "anthropic/claude-haiku-5.5",
    "sonnet": "anthropic/claude-sonnet-5.5",
}
SIMULATOR_MODEL = MODELS["haiku"]
JUDGE_MODEL = MODELS["sonnet"]
# USD per 1M tokens (input, output), OpenRouter catalog on 2026-10-24. Only for the estimate before a run.
PRICES = {
    MODELS["haiku"]: (0.10, 0.50),
    MODELS["sonnet"]: (2.00, 10.00),
}


def settings_for(config: str, base: Settings) -> Settings:
    """The core as production runs it, with the named model and without side effects outside the database.

    Fallback models are off: a failure shows up as an error, not as another model's answer.
    Handoffs never reach a real manager chat.
    """

    common = {"handoff_provider": "mock", "default_business_id": None}
    if config == "mock":
        return base.model_copy(
            update={**common, "ai_mode": "mock", "small_model_provider": "mock", "big_model_provider": "mock"}
        )
    if config not in MODELS:
        raise ValueError(f"неизвестная конфигурация {config!r}, есть: {', '.join(MODELS)}")
    return base.model_copy(
        update={
            **common,
            "ai_mode": "production",
            "small_model_provider": "none",
            "big_model_provider": "openrouter_big",
            "openrouter_big_model": MODELS[config],
            "openrouter_fallback_models": "",
        }
    )
