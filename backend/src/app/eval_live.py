"""Live dialog through the whole core with a real model. Compare models and tone.

    python -m app.eval_live                                   # models from .env
    python -m app.eval_live --provider openrouter --small google/gemini-2.5-flash-lite --big google/gemini-2.5-flash
    python -m app.eval_live --provider gemini                 # Google AI Studio directly (GEMINI_API_KEY)
    python -m app.eval_live --provider openai_compat --small deepseek-chat --big deepseek-chat

Needs Postgres (scripts/local-db.ps1 start). Each run uses fresh phone numbers,
so runs do not share memory. Prints every reply with route, model, latency,
cost and handoff, then totals.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time

from app.config import get_settings
from app.container import build_agent, build_runtime
from app.domain.models import InboundMessage
from app.migrate import upgrade_database
from app.seed import seed

# One buyer over two channels, then a Kyrgyz speaker and an off-topic caller.
SCRIPT: list[tuple[str, str]] = [
    ("whatsapp", "Здравствуйте! Квартира на Чуй ещё продаётся?"),
    ("whatsapp", "для себя, живём вдвоём с женой"),
    ("whatsapp", "а можно дешевле что-нибудь?"),
    ("whatsapp", "а рассрочка у вас есть?"),
    ("whatsapp", "вы вообще бот?"),
    ("voice", "Алло, я вчера писал вам про квартиру"),
    ("voice", "давайте посмотрим однушку у Филармонии в субботу в 11:00"),
    ("telegram:ky", "Салам, Джалдагы квартиранын баасы канча?"),
    ("telegram:ky", "рахмат, ойлонуп көрөйүн"),
    ("telegram:other", "какая погода завтра в Бишкеке?"),
]


async def run(args: argparse.Namespace) -> int:
    settings = get_settings().model_copy(update=_overrides(args))
    if settings.mock_mode:
        print("AI_MODE=mock: set AI_MODE=production in .env or pass --provider", file=sys.stderr)
        return 2
    runtime = build_runtime(settings)
    suffix = random.randint(100000, 999999)
    users = {
        "whatsapp": f"+996555{suffix}",
        "voice": f"+996555{suffix}",
        "telegram:ky": f"tg-ky-{suffix}",
        "telegram:other": f"tg-x-{suffix}",
    }
    total_cost = 0.0
    latencies: list[int] = []
    try:
        async with runtime.session_factory() as session:
            await seed(session)
            await session.commit()
        for key, text in SCRIPT:
            channel = key.split(":")[0]
            async with runtime.session_factory() as session:
                agent = build_agent(session, runtime)
                started = time.perf_counter()
                response = await agent.process_message(
                    InboundMessage(channel=channel, external_user_id=users[key], text=text)
                )
                await session.commit()
            elapsed = int((time.perf_counter() - started) * 1000)
            latencies.append(elapsed)
            total_cost += response.usage.estimated_cost
            flag = f" HANDOFF:{response.handoff_reason}" if response.handoff_required else ""
            # Why the core replaced the model's draft, if it did.
            fallback = [step for step in response.logs if step.startswith(("validator:", "grounded_fallback", "role_fallback"))]
            if fallback:
                flag += f" FALLBACK:{','.join(fallback)}"
            print(f"\n[{channel}] Клиент: {text}")
            print(f"  Plumo: {response.response_text}")
            print(
                f"  ↳ {response.route}/{response.route_reason} · {response.model_used} · "
                f"{elapsed} ms · ${response.usage.estimated_cost:.6f}{flag}"
            )
    finally:
        await runtime.providers.aclose()
        await runtime.engine.dispose()
    latencies.sort()
    print(
        f"\nturns={len(latencies)} total=${total_cost:.5f} "
        f"avg=${total_cost / len(latencies):.6f}/turn "
        f"p50={latencies[len(latencies) // 2]} ms max={latencies[-1]} ms"
    )
    return 0


def _overrides(args: argparse.Namespace) -> dict:
    if not args.provider:
        return {}
    update = {
        "ai_mode": "production",
        "small_model_provider": f"{args.provider}_small",
        "big_model_provider": f"{args.provider}_big",
    }
    prefix = {"openrouter": "openrouter", "gemini": "gemini", "openai_compat": "llm"}[args.provider]
    if args.small:
        update[f"{prefix}_small_model"] = args.small
    if args.big:
        update[f"{prefix}_big_model"] = args.big
    return update


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=["openrouter", "gemini", "openai_compat"])
    parser.add_argument("--small", help="model id for the small tier")
    parser.add_argument("--big", help="model id for the big tier")
    args = parser.parse_args()
    upgrade_database()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
