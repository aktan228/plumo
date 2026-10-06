"""Ping OpenRouter without PostgreSQL.

    python -m app.ping_llm
"""

import asyncio
import sys

from app.config import get_settings
from app.domain.errors import ProviderUnavailable
from app.infrastructure.ai.openrouter_llm import OpenRouterLLMProvider


async def main() -> int:
    settings = get_settings()
    try:
        provider = OpenRouterLLMProvider(
            "openrouter_small",
            settings.openrouter_small_model,
            base_url=settings.openrouter_base_url,
        )
    except ProviderUnavailable as exc:
        print(exc.message)
        return 1
    try:
        payload = await provider.complete("Скажи, что Plumo подключил Gemini через OpenRouter.")
    except ProviderUnavailable as exc:
        print(exc.message)
        return 1
    print(f"model: {provider.model}")
    print(f"reply: {payload['text']}")
    print(
        "tokens: "
        f"{payload['usage']['input_tokens']}+{payload['usage']['output_tokens']} "
        f"cost={payload['usage']['estimated_cost']:.6f}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    raise SystemExit(asyncio.run(main()))
