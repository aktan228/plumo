"""Multi-turn dialog eval through the whole agent core.

    python -m app.dialog_eval --mock                          # whole pipeline without network, free
    python -m app.dialog_eval --config haiku                  # 10 personas x 3 repeats
    python -m app.dialog_eval --config haiku sonnet --persona family haggler --repeat 1
    python -m app.dialog_eval --config haiku --repeat 2 --turns 8 --yes
    python -m app.dialog_eval --rejudge work/dialog_eval/<time>   # grade again only dialogs the judge failed on

A cheap model (Haiku) plays the customer from a persona card; the agent is the
real core (build_agent -> process_message, Telegram channel, demo business);
Sonnet grades each dialog blind. Needs Postgres (./dev.sh db) and, for a live
run, OPENROUTER_API_KEY. Handoffs go to a mock provider, never to the manager chat.
Results: work/dialog_eval/<time>/report.md and results.json (work/ is git-ignored).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from app.config import get_settings
from app.container import build_runtime
from app.dialog_eval.checks import catalog_numbers, check_dialog
from app.dialog_eval.configs import JUDGE_MODEL, MODELS, PRICES, SIMULATOR_MODEL, settings_for
from app.dialog_eval.judge import MockJudge, ModelJudge
from app.dialog_eval.personas import BY_ID, PERSONAS
from app.dialog_eval.report import write_report
from app.dialog_eval.runner import Dialog, Turn, run_dialog
from app.dialog_eval.simulator import MockSimulator, ModelSimulator
from app.seed import seed

# Token sizes for the estimate, from the bench and live turns: agent prompt with catalog hits and history,
# the customer's card and dialog, the judge's rubric, catalog and dialog.
AGENT_TOKENS = (3000, 200)
SIMULATOR_TOKENS = (1200, 80)
JUDGE_TOKENS = (5000, 1500)


def _usd(model: str, tokens: tuple[int, int]) -> float:
    price_in, price_out = PRICES[model]
    return (tokens[0] * price_in + tokens[1] * price_out) / 1_000_000


def estimate(configs: list[str], dialogs_per_config: int, turns: int) -> float:
    """Upper bound: every dialog runs to the turn limit."""

    total = 0.0
    for config in configs:
        per_dialog = turns * _usd(MODELS[config], AGENT_TOKENS) + (turns - 1) * _usd(SIMULATOR_MODEL, SIMULATOR_TOKENS)
        per_dialog += _usd(JUDGE_MODEL, JUDGE_TOKENS)
        total += dialogs_per_config * per_dialog
    return total


async def run_eval(
    runtimes: dict,
    personas: list,
    repeat: int,
    turns: int,
    simulator,
    judge,
    concurrency: int,
    progress: bool = True,
) -> list[Dialog]:
    """Every (config, persona, attempt) dialog, `concurrency` at a time, then checks and the judge."""

    run_id = f"{datetime.now():%m%d%H%M}{random.randint(100, 999)}"
    gate = asyncio.Semaphore(max(1, concurrency))
    allowed = catalog_numbers()

    async def one(config: str, persona, attempt: int) -> Dialog:
        async with gate:
            dialog = await run_dialog(runtimes[config], config, persona, attempt, simulator, run_id, turns)
            dialog.checks = check_dialog(dialog, persona, allowed)
            await judge.grade(dialog, persona)
        if progress:
            score = dialog.judge.get("scores")
            mark = "✗" if dialog.checks["critical"] else "✓"
            mean = (
                f"{sum(v for v in score.values() if v) / max(1, sum(1 for v in score.values() if v)):.1f}"
                if score
                else "-"
            )
            print(f"  {config:7} {persona.id:9} #{attempt} {mark} {len(dialog.turns):2} реплик · {dialog.end:12} · судья {mean}")
        return dialog

    jobs = [one(config, persona, attempt) for config in runtimes for persona in personas for attempt in range(1, repeat + 1)]
    return list(await asyncio.gather(*jobs))


def load_dialogs(data: dict) -> list[Dialog]:
    dialogs = []
    for raw in data["dialogs"]:
        turns = [Turn(**turn) for turn in raw.pop("turns")]
        dialogs.append(Dialog(**raw, turns=turns))
    return dialogs


async def rejudge(folder: Path) -> int:
    """Grade again the dialogs whose verdict failed; the dialogs themselves are not rerun."""

    from app.bench.run import judge_catalog

    data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    dialogs = load_dialogs(data)
    failed = [item for item in dialogs if "scores" not in item.judge]
    print(f"Без оценки судьи: {len(failed)} из {len(dialogs)}. Оценка стоимости: ~${len(failed) * _usd(JUDGE_MODEL, JUDGE_TOKENS):.2f}")
    if not failed:
        return 0
    judge = ModelJudge(JUDGE_MODEL, judge_catalog())
    try:
        await asyncio.gather(*(judge.grade(item, BY_ID[item.persona]) for item in failed))
    finally:
        await judge.aclose()
    meta = data["meta"]
    meta["judge_cost"] = meta.get("judge_cost", 0.0) + judge.cost
    write_report(folder, dialogs, meta["configs"], meta)
    print(f"Оценено заново: {sum('scores' in item.judge for item in failed)}, потрачено ~${judge.cost:.3f}. Отчёт: {folder / 'report.md'}")
    return 0


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Стенд оценки диалогов Plumo")
    parser.add_argument("--config", nargs="+", default=["haiku"], choices=list(MODELS), help="конфигурации агента")
    parser.add_argument("--persona", nargs="+", choices=list(BY_ID), help="только эти персоны")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--turns", type=int, default=10, help="максимум реплик агента в диалоге")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--mock", action="store_true", help="без сети: mock-модель агента, клиент по скрипту, mock-судья")
    parser.add_argument("--yes", action="store_true", help="не спрашивать подтверждение расхода")
    parser.add_argument("--out", default="work/dialog_eval")
    parser.add_argument("--rejudge", metavar="FOLDER", help="папка прошлого прогона: оценить заново диалоги без оценки")
    args = parser.parse_args(argv)
    load_dotenv()
    if args.rejudge:
        return await rejudge(Path(args.rejudge))

    personas = [BY_ID[name] for name in args.persona] if args.persona else list(PERSONAS)
    configs = ["mock"] if args.mock else list(dict.fromkeys(args.config))
    per_config = len(personas) * args.repeat
    print(f"Конфигурации: {', '.join(configs)}. Персон: {len(personas)}, повторов: {args.repeat}, лимит реплик: {args.turns}.")
    if not args.mock:
        cost = estimate(configs, per_config, args.turns)
        print(f"Диалогов: {per_config * len(configs)}. Оценка стоимости (все диалоги до лимита): до ~${cost:.2f}")
        if not args.yes:
            answer = input("Запустить? [y/N] ").strip().lower()
            if answer not in ("y", "yes", "д", "да"):
                print("Не запускаю.")
                return 1
        from app.bench.run import ModelSpec, preflight

        problems = await preflight([ModelSpec("eval", "openrouter", SIMULATOR_MODEL)], None)
        if problems:
            print("Не запускаю, деньги не потрачены:")
            for problem in problems:
                print(f"  - {problem}")
            return 1

    from app.migrate import upgrade_database

    # Alembic's env.py calls asyncio.run: a thread gives it a loop of its own.
    await asyncio.to_thread(upgrade_database)
    base = get_settings()
    runtimes = {}
    simulator = MockSimulator() if args.mock else ModelSimulator(SIMULATOR_MODEL)
    if args.mock:
        judge = MockJudge()
    else:
        from app.bench.run import judge_catalog

        judge = ModelJudge(JUDGE_MODEL, judge_catalog())
    out = Path(args.out) / datetime.now().strftime("%Y%m%d-%H%M%S")
    started = time.perf_counter()
    try:
        for config in configs:
            runtimes[config] = build_runtime(settings_for(config, base))
        first = next(iter(runtimes.values()))
        async with first.session_factory() as session:
            await seed(session)
            await session.commit()
        dialogs = await run_eval(runtimes, personas, args.repeat, args.turns, simulator, judge, args.concurrency)
    finally:
        for runtime in runtimes.values():
            await runtime.providers.aclose()
            await runtime.engine.dispose()
        await simulator.aclose()
        await judge.aclose()

    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "configs": configs,
        "personas": len(personas),
        "repeat": args.repeat,
        "turns": args.turns,
        "simulator": "mock" if args.mock else SIMULATOR_MODEL,
        "judge": "mock" if args.mock else JUDGE_MODEL,
        "agent_cost": sum(item.agent_cost for item in dialogs),
        "simulator_cost": sum(item.simulator_cost for item in dialogs),
        "judge_cost": judge.cost,
    }
    report = write_report(out, dialogs, configs, meta)
    # The mock model reports made-up costs; nothing was spent.
    spent = 0.0 if args.mock else meta["agent_cost"] + meta["simulator_cost"] + meta["judge_cost"]
    print("\n" + report.split("## По персонам")[0])
    print(f"Потрачено: ~${spent:.3f} за {time.perf_counter() - started:.0f} с. Отчёт: {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    raise SystemExit(asyncio.run(main()))
