"""Ping the configured big model with the real sales prompt, without PostgreSQL.

    python -m app.ping_llm
    python -m app.ping_llm --provider openrouter_big --model google/gemini-3.1-flash-lite
    python -m app.ping_llm --repeat 3        # second and later calls show the implicit cache

Prints the model that answered (a fallback, if the first one is retired),
latency, tokens (cached ones too) and cost. One call costs a fraction of a cent.
"""

import argparse
import asyncio
import sys
import time
from datetime import UTC, datetime
from uuid import uuid4

from app.config import get_settings
from app.container import _llm_provider
from app.domain.errors import ProviderTransientError, ProviderUnavailable
from app.domain.models import AgentContext, Business, Customer, KnowledgeHit, KnowledgeItem, RouteDecision
from app.domain.phrases import agent_instructions


def _context(text: str) -> AgentContext:
    now = datetime.now(UTC)
    business = Business(
        uuid4(),
        "Demo Realty",
        "Агентство недвижимости в Бишкеке",
        "09:00-18:00",
        {"address": "Бишкек, проспект Чуй, 114"},
        "Не выдумывать.",
        now,
        now,
    )
    item = KnowledgeItem(
        uuid4(), business.id, "property", "Квартира на Чуй", "2 комнаты, 58 м², 5 этаж, 85 000 USD. Статус: в продаже.", {}, True, now, now
    )
    customer = Customer(uuid4(), "+996555000111", "ru", "active", None, "whatsapp", None, now, now, business_id=business.id)
    return AgentContext(
        agent_instructions=agent_instructions(business.name, "Плюмо", "voice"),
        business=business,
        knowledge=[KnowledgeHit(item, 5.0)],
        customer=customer,
        summary=None,
        recent_messages=[],
        current_message=text,
        language="ru",
        channel="voice",
    )


async def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Проверка живой модели на настоящем промпте")
    parser.add_argument("--provider", default=settings.big_model_provider, help="gemini_big, openrouter_big, ...")
    parser.add_argument("--model", help="переопределить model id")
    parser.add_argument("--text", default="Еще продается квартира за 85000? Сколько там метров?")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args(argv)
    if args.model:
        family = args.provider.rpartition("_")[0] or args.provider
        tier = "small" if args.provider.endswith("_small") else "big"
        setattr(settings, f"{family}_{tier}_model", args.model)
    try:
        provider = _llm_provider(args.provider, settings)
    except ProviderUnavailable as exc:
        print(exc.message)
        return 1
    if provider is None:
        print(f"Неизвестный провайдер {args.provider}")
        return 1
    print(f"provider: {args.provider}  models: {provider.models}  extra: {provider.extra_body}")
    try:
        for _ in range(max(1, args.repeat)):
            started = time.perf_counter()
            generation = await provider.generate_response(_context(args.text), RouteDecision("big", "ping", 1.0))
            elapsed = int((time.perf_counter() - started) * 1000)
            print(f"\nmodel: {generation.model_used}  latency: {elapsed} ms")
            print(f"reply: {generation.text}")
            print(
                f"tokens: in={generation.input_tokens} out={generation.output_tokens} "
                f"confidence={generation.confidence} cost=${generation.estimated_cost:.6f}"
            )
    except (ProviderUnavailable, ProviderTransientError) as exc:
        print(exc.message)
        return 1
    finally:
        await provider.aclose()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    raise SystemExit(asyncio.run(main()))
