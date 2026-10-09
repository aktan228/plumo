"""CLI demo of the mock agent. No frontend and no real model required.

    python -m app.demo
    python -m app.demo --interactive
"""

import argparse
import asyncio
import sys

from app.config import get_settings
from app.container import build_agent, build_runtime
from app.correlation import correlation_id, request_id
from app.domain.models import InboundMessage
from app.migrate import upgrade_database
from app.seed import seed

SCENARIO = (
    "Еще продается квартира за 85000?",
    "А рассрочка есть?",
)


def _configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        return


def _print_turn(user_text: str, response) -> None:
    print(f"Client > {user_text}")
    print()
    print(f"Plumo > {response.response_text}")
    print()
    if response.handoff_required:
        print("[HANDOFF CREATED]")
        print()
    sources = ", ".join(item.title for item in response.knowledge_sources) or "-"
    print(f"Customer ID: {response.customer_id}")
    print(f"Conversation ID: {response.conversation_id}")
    print("Channel: cli")
    print(f"Language: {response.language}")
    print(f"Router: {response.route} ({response.route_reason}) {response.confidence:.2f}")
    print(f"Model: {response.model_used}")
    print(f"Knowledge: {sources}")
    print(f"Cost: {response.usage.estimated_cost:.3f}")
    print(f"Latency: {response.latency_ms}ms")
    print(f"Correlation: {response.correlation_id}")
    print()


async def _run(interactive: bool) -> None:
    settings = get_settings()
    runtime = build_runtime(settings)
    async with runtime.session_factory() as session:
        await seed(session)
        await session.commit()
        agent = build_agent(session, runtime)
        if interactive:
            print("plumo demo. пустая строка — выход.")
            print()
            while True:
                try:
                    text = input("Client > ").strip()
                except EOFError:
                    break
                if not text:
                    break
                response = await _turn(agent, text)
                print()
                print(f"Plumo > {response.response_text}")
                print()
                if response.handoff_required:
                    print("[HANDOFF CREATED]")
                print(
                    f"{response.customer_id}  {response.route}/{response.route_reason}  "
                    f"{response.model_used}  {response.usage.estimated_cost:.3f}"
                )
                print()
        else:
            for text in SCENARIO:
                response = await _turn(agent, text)
                _print_turn(text, response)
        await session.commit()
    await runtime.engine.dispose()


async def _turn(agent, text: str):
    cid = correlation_id.set("demo")
    rid = request_id.set("demo")
    try:
        return await agent.process_message(
            InboundMessage(
                channel="cli",
                external_user_id="cli-demo",
                text=text,
                correlation_id="demo",
                request_id="demo",
            )
        )
    finally:
        correlation_id.reset(cid)
        request_id.reset(rid)


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="Plumo mock demo")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    upgrade_database()
    asyncio.run(_run(args.interactive))


if __name__ == "__main__":
    main()
