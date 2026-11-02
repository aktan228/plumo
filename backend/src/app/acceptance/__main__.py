"""Acceptance run J-03: scenarios through the real core, not the bare model.

    python -m app.acceptance --mock               # whole pipeline without network, $0
    python -m app.acceptance --limit 5            # small paid run first (AI_MODE and keys from .env)
    python -m app.acceptance --only fact language --max-usd 1

Each turn goes through AgentService as in production: retrieval, model, validator,
fallbacks, actions, handoff. The checks look at the final reply and actions. The run
uses its own database (`<name>_acceptance` next to DATABASE_URL): the catalog is seeded
there, and every scenario runs in a transaction that is rolled back. Handoffs never
notify anyone (mock provider). It stops before the next scenario once `--max-usd` is spent.

Report: work/acceptance/<time>/report.md and results.json; by language separately.
"""

import argparse
import asyncio
import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.acceptance.scenarios import SCENARIOS, SETUP
from app.bench.checks import Check, language_of, run_checks
from app.bench.scenarios import CATEGORIES, Scenario
from app.config import get_settings
from app.container import build_agent, build_runtime
from app.domain.models import AgentContext, Conversation, CustomerSummary, InboundMessage, KnowledgeHit, Message, utcnow
from app.infrastructure.database.base import Base
from app.infrastructure.database.models import UsageLogRow
from app.infrastructure.database.repositories import (
    ConversationRepository,
    CustomerRepository,
    KnowledgeRepository,
    MessageRepository,
    SummaryRepository,
)
from app.infrastructure.database.session import create_engine, create_session_factory
from app.seed import seed

CATEGORIES = {**CATEGORIES, "fact": "Факты и похожие объекты", "handoff": "Передача и обещания"}


@dataclass
class Result:
    id: str
    category: str
    language: str
    message: str
    reply: str
    handoff: bool
    actions: list[str]
    steps: list[str]
    cost_usd: float
    checks: list[dict]
    error: str | None = None

    @property
    def critical(self) -> list[dict]:
        return [check for check in self.checks if check["critical"] and not check["passed"]]

    @property
    def passed(self) -> bool:
        return all(check["passed"] for check in self.checks)


def acceptance_url(database_url: str) -> str:
    url = make_url(database_url)
    name = f"{url.database or 'plumo'}_acceptance"
    return url.set(database=name).render_as_string(hide_password=False)


async def prepare(url: str) -> None:
    """Create the run's own database and the demo catalog. Never touches the working database."""

    parsed = make_url(url)
    assert parsed.database and parsed.database.endswith("_acceptance"), parsed.database
    admin = parsed.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    conn = await asyncpg.connect(admin)
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", parsed.database):
            await conn.execute(f'CREATE DATABASE "{parsed.database}"')
    finally:
        await conn.close()
    engine = create_engine(url, null_pool=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with create_session_factory(engine)() as session:
        await seed(session)
        await session.commit()
    await engine.dispose()


async def run_one(runtime, factory, scenario: Scenario, index: int) -> Result:
    async with factory() as session:
        try:
            agent = build_agent(session, runtime)
            business = (await agent.businesses.list_all())[0]
            for tag in scenario.tags:
                if tag.startswith("setup:"):
                    await SETUP[tag.removeprefix("setup:")](session, business.id)
            channel = scenario.channel
            if channel == "whatsapp" and not scenario.has_phone:
                channel = "telegram"
            external = f"+99655577{index:04d}" if channel in ("whatsapp", "voice") else f"acceptance-{index}"
            inbound = InboundMessage(channel=channel, external_user_id=external, text=scenario.message, business_id=business.id)
            if scenario.history or scenario.summary or scenario.need:
                await _prepare_dialog(session, agent, inbound, business.id, scenario)
            response = await agent.process_message(inbound)
            # Mock providers log a made-up price per reply; only a live model costs money.
            cost = 0.0 if runtime.settings.mock_mode else float(
                await session.scalar(select(func.coalesce(func.sum(UsageLogRow.estimated_cost), 0))) or 0
            )
            context = await _checking_context(session, agent, business, scenario)
        except Exception as exc:  # one broken scenario is a finding, not the end of the run
            await session.rollback()
            failed = [Check("reply", False, f"{type(exc).__name__}: {str(exc)[:200]}")]
            return _result(scenario, "", False, [], [], 0.0, failed, error=type(exc).__name__)
        await session.rollback()
    final = SimpleNamespace(text=response.response_text, actions=response.actions, handoff_required=response.handoff_required)
    checks = run_checks(scenario, context, final, None)
    return _result(
        scenario, response.response_text, response.handoff_required,
        [str(action.type) for action in response.actions], response.logs, cost, checks,
    )


async def _prepare_dialog(session, agent, inbound: InboundMessage, business_id, scenario: Scenario) -> None:
    customer = await agent.resolver.resolve_customer(inbound, business_id)
    now = utcnow()
    if scenario.need:
        customer.need = scenario.need
        await CustomerRepository(session).save(customer)
    if scenario.summary:
        await SummaryRepository(session).upsert(
            CustomerSummary(customer.id, scenario.summary, scenario.need, "ru", "active", [], now)
        )
    if scenario.history:
        conversation = await ConversationRepository(session).add(
            Conversation(uuid4(), customer.id, inbound.channel, now, None, None, now, now, business_id=business_id)
        )
        messages = MessageRepository(session)
        for role, text in scenario.history:
            await messages.add(Message(uuid4(), conversation.id, customer.id, role, text, now, {}, now))


async def _checking_context(session, agent, business, scenario: Scenario) -> AgentContext:
    """Facts are checked against the whole current catalog, not only what this turn retrieved."""

    items = await KnowledgeRepository(session).list_active(business.id)
    return AgentContext(
        agent_instructions="",
        business=business,
        knowledge=[KnowledgeHit(item, 1.0) for item in items],
        customer=SimpleNamespace(phone=None),
        summary=None,
        recent_messages=[SimpleNamespace(role=role, text=text) for role, text in scenario.history],
        current_message=scenario.message,
        language="ru",
        channel=scenario.channel,
    )


def _result(scenario, reply, handoff, actions, steps, cost, checks, error=None) -> Result:
    language = language_of(scenario.message)
    return Result(
        id=scenario.id,
        category=scenario.category,
        language=language if language in ("ru", "ky", "mixed", "en") else "ru",
        message=scenario.message,
        reply=reply,
        handoff=handoff,
        actions=actions,
        steps=[step for step in steps if ":" in step or step in ("clarify_object", "grounded_fallback")],
        cost_usd=round(cost, 6),
        checks=[{"name": check.name, "passed": check.passed, "critical": check.critical, "detail": check.detail} for check in checks],
        error=error,
    )


def report(results: list[Result], mode: str, spent: float, seconds: float) -> str:
    total = len(results)
    critical = [result for result in results if result.critical]
    passed = sum(result.passed for result in results)
    lines = [
        f"# Приёмочный набор J-03 — {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        "",
        f"Режим модели: **{mode}**. Сценариев: {total}. Расход: ${spent:.4f}. Время: {seconds:.0f} с.",
        "",
        f"- Критических ошибок: **{len(critical)}** (цель — 0)",
        f"- Все проверки пройдены: **{passed}/{total}** ({passed * 100 // max(total, 1)}%); остальное смотрит человек (цель — 90% принятых)",
        "",
        "## По языкам",
        "",
        "| Язык | Сценариев | Все проверки | Критические |",
        "|---|---|---|---|",
    ]
    by_language: dict[str, list[Result]] = defaultdict(list)
    for result in results:
        by_language[result.language].append(result)
    for language in ("ru", "ky", "mixed", "en"):
        group = by_language.get(language, [])
        if group:
            lines.append(f"| {language} | {len(group)} | {sum(r.passed for r in group)} | {sum(bool(r.critical) for r in group)} |")
    lines += ["", "## По группам", "", "| Группа | Сценариев | Все проверки | Критические |", "|---|---|---|---|"]
    by_category: dict[str, list[Result]] = defaultdict(list)
    for result in results:
        by_category[result.category].append(result)
    for category, group in by_category.items():
        lines.append(f"| {CATEGORIES.get(category, category)} | {len(group)} | {sum(r.passed for r in group)} | {sum(bool(r.critical) for r in group)} |")
    failed = [result for result in results if not result.passed]
    if failed:
        lines += ["", "## Что не прошло", ""]
        for result in sorted(failed, key=lambda r: (not r.critical, r.id)):
            mark = "КРИТИЧНО" if result.critical else "проверить"
            reasons = "; ".join(f"{c['name']}: {c['detail']}" if c["detail"] else c["name"] for c in result.checks if not c["passed"])
            lines += [
                f"### {result.id} — {mark}",
                f"- Клиент: {result.message}",
                f"- Ответ: {result.reply or '—'}",
                f"- Передача: {'да' if result.handoff else 'нет'}; действия: {', '.join(result.actions) or '—'}; шаги ядра: {', '.join(result.steps) or '—'}",
                f"- Не прошло: {reasons}",
                "",
            ]
    return "\n".join(lines) + "\n"


async def main(args) -> int:
    base = get_settings()
    url = acceptance_url(base.database_url)
    overrides = {"database_url": url, "handoff_provider": "mock", "default_business_id": None}
    if args.mock:
        overrides["ai_mode"] = "mock"
    settings = base.model_copy(update=overrides)
    scenarios = [s for s in SCENARIOS if not args.only or s.category in args.only or s.id in args.only]
    if args.limit:
        scenarios = scenarios[: args.limit]
    mode = "mock" if settings.mock_mode else f"live: {settings.big_model_provider}"
    print(f"{len(scenarios)} scenarios, model {mode}, database {make_url(url).database}, stop at ${args.max_usd:.2f}")
    await prepare(url)
    runtime = build_runtime(settings)
    factory = create_session_factory(runtime.engine)
    results: list[Result] = []
    spent = 0.0
    started = time.monotonic()
    try:
        for index, scenario in enumerate(scenarios):
            if spent >= args.max_usd:
                print(f"Stopped: ${spent:.4f} spent, limit ${args.max_usd:.2f}")
                break
            result = await run_one(runtime, factory, scenario, index)
            spent += result.cost_usd
            results.append(result)
            status = "ok" if result.passed else ("CRITICAL" if result.critical else "check")
            print(f"[{index + 1}/{len(scenarios)}] {scenario.id}: {status}  ${spent:.4f}")
    finally:
        await runtime.providers.aclose()
        await runtime.engine.dispose()
    out = Path("work/acceptance") / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    text = report(results, mode, spent, time.monotonic() - started)
    (out / "report.md").write_text(text, encoding="utf-8")
    (out / "results.json").write_text(
        json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    critical = sum(bool(result.critical) for result in results)
    print(f"\n{sum(r.passed for r in results)}/{len(results)} passed all checks, {critical} critical, ${spent:.4f}. Report: {out / 'report.md'}")
    return 1 if critical else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plumo acceptance set through the real core")
    parser.add_argument("--mock", action="store_true", help="mock model: no network, no cost")
    parser.add_argument("--only", nargs="*", default=[], help="categories or scenario ids")
    parser.add_argument("--limit", type=int, default=0, help="first N scenarios only")
    parser.add_argument("--max-usd", type=float, default=1.0, help="stop before the next scenario once spent")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
