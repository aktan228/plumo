"""Dialog eval in --mock: scripted customers through the whole core, checks, mock judge, report. No network."""

import json

from app.container import build_runtime
from app.dialog_eval.__main__ import run_eval
from app.dialog_eval.configs import settings_for
from app.dialog_eval.judge import MockJudge
from app.dialog_eval.personas import BY_ID
from app.dialog_eval.report import write_report
from app.dialog_eval.simulator import MockSimulator
from app.seed import seed


async def test_mock_pipeline_writes_report(session, settings, engine, tmp_path):
    await seed(session)
    await session.commit()
    runtime = build_runtime(settings_for("mock", settings), engine=engine)
    personas = [BY_ID["family"], BY_ID["unknowns"]]
    dialogs = await run_eval({"mock": runtime}, personas, 2, 6, MockSimulator(), MockJudge(), 2, progress=False)

    assert len(dialogs) == 4
    assert all(item.error is None for item in dialogs)
    # Every attempt is its own customer: runs never share memory.
    assert len({item.user_id for item in dialogs}) == 4
    for dialog in dialogs:
        assert len(dialog.turns) == len(BY_ID[dialog.persona].mock_lines)
        assert all(turn.agent for turn in dialog.turns)
        assert dialog.checks and dialog.judge["scores"]
    unknowns = [item for item in dialogs if item.persona == "unknowns"]
    assert all("no_knowledge" in item.checks["handoffs"] for item in unknowns)

    meta = {"configs": ["mock"], "personas": 2, "repeat": 2, "turns": 6, "simulator": "mock", "judge": "mock",
            "agent_cost": 0.0, "simulator_cost": 0.0, "judge_cost": 0.0}
    report = write_report(tmp_path, dialogs, ["mock"], meta)
    assert "## Итог по конфигурациям" in report and "## Худшие диалоги" in report
    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert len(data["dialogs"]) == 4 and "mock" in data["summary"]


def test_eval_never_notifies_the_real_manager(settings):
    live = settings.model_copy(update={"handoff_provider": "telegram"})
    for config in ("mock", "haiku", "sonnet"):
        assert settings_for(config, live).handoff_provider == "mock"
    assert settings_for("haiku", live).openrouter_fallback_models == ""
