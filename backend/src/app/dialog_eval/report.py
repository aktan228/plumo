"""report.md and results.json for a dialog eval run."""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.dialog_eval.judge import CRITERIA, mean_score
from app.dialog_eval.runner import Dialog

WORST_SHOWN = 3


def _pct(part: int, total: int) -> str:
    return f"{100 * part / total:.0f}%" if total else "-"


def _avg(values: list[float], digits: int = 2) -> str:
    return f"{statistics.mean(values):.{digits}f}" if values else "-"


def _quantile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def summary_row(dialogs: list[Dialog]) -> dict[str, Any]:
    checks = [item.checks for item in dialogs]
    turns = [turn for item in dialogs for turn in item.turns if turn.agent]
    judged = [item.judge for item in dialogs if "scores" in item.judge]
    row: dict[str, Any] = {
        "dialogs": len(dialogs),
        "errors": sum(item.error is not None for item in dialogs),
        "phone": _pct(sum(c["phone_saved"] for c in checks), len(dialogs)),
        "meeting": _pct(sum(c["meeting"] for c in checks), len(dialogs)),
        "left": _pct(sum(c["end"] in ("declined", "left") for c in checks), len(dialogs)),
        "repeats": sum(len(c["repeated_questions"]) for c in checks),
        "avg_chars": _avg([c["avg_chars"] for c in checks if c["agent_turns"]], 0),
        "long_share": _pct(sum(c["long_replies"] for c in checks), len(turns)),
        "wrong_language": _pct(sum(len(c["wrong_language"]) for c in checks), len(turns)),
        "substituted": _pct(sum(c["substituted"] for c in checks), len(turns)),
        "invented": sum(len(c["invented_numbers"]) for c in checks),
        "wrong_offer": sum(len(c["wrong_offer"]) for c in checks),
        "missing_handoff": sum(bool(c["missing_handoff"]) for c in checks),
        "unwarranted_handoff": sum(len(c["unwarranted_handoffs"]) for c in checks),
        "p50": _quantile([turn.latency_ms for turn in turns], 0.5),
        "p90": _quantile([turn.latency_ms for turn in turns], 0.9),
        "cost": f"${statistics.mean([item.agent_cost for item in dialogs]):.4f}" if dialogs else "-",
        "judge_mean": _avg([value for value in (mean_score(item) for item in judged) if value is not None]),
        "judge_critical": sum(bool(item.get("critical_error")) for item in judged),
    }
    for key in CRITERIA:
        row[key] = _avg([item["scores"][key] for item in judged if item["scores"].get(key) is not None])
    return row


def _badness(dialog: Dialog) -> tuple:
    score = mean_score(dialog.judge) if "scores" in dialog.judge else None
    critical = dialog.checks.get("critical") or dialog.judge.get("critical_error")
    return (not critical, score if score is not None else 5.0)


def write_report(out: Path, dialogs: list[Dialog], configs: list[str], meta: dict[str, Any]) -> str:
    lines = [
        "# Стенд оценки диалогов Plumo",
        "",
        f"Дата: {datetime.now():%Y-%m-%d %H:%M}. Персон: {meta['personas']}, повторов: {meta['repeat']}, "
        f"лимит реплик: {meta['turns']}. Клиент: `{meta['simulator']}`. Судья: `{meta['judge']}` (не знает конфигурацию).",
        f"Потрачено: агент ${meta['agent_cost']:.3f}, клиент-симулятор ${meta['simulator_cost']:.3f}, "
        f"судья ${meta['judge_cost']:.3f}.",
        "",
        "Диалоги идут через всё ядро (валидатор, подстановки, передачи), оценивается текст, который увидел бы клиент.",
        "",
        "## Итог по конфигурациям",
        "",
        "| Конфигурация | Диалогов | Телефон | Встреча | Ушёл | Повторы вопросов | Ср. длина | > 3 предл. | Не тот язык | Подмены ядра | Чужие суммы | Не тот тип сделки | Нет нужной передачи | Лишняя передача | p50 | p90 | $/диалог | Ошибки |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows = {config: summary_row([item for item in dialogs if item.config == config]) for config in configs}
    for config, r in rows.items():
        lines.append(
            f"| {config} | {r['dialogs']} | {r['phone']} | {r['meeting']} | {r['left']} | {r['repeats']} | {r['avg_chars']} | "
            f"{r['long_share']} | {r['wrong_language']} | {r['substituted']} | {r['invented']} | {r['wrong_offer']} | "
            f"{r['missing_handoff']} | {r['unwarranted_handoff']} | {r['p50']} мс | {r['p90']} мс | {r['cost']} | {r['errors']} |"
        )
    lines += ["", "## Оценки судьи (1–5)", ""]
    lines.append("| Конфигурация | " + " | ".join(CRITERIA.values()) + " | Среднее | Крит. ошибки |")
    lines.append("| --- | " + " | ".join("---" for _ in CRITERIA) + " | --- | --- |")
    for config, r in rows.items():
        lines.append(
            f"| {config} | " + " | ".join(r[key] for key in CRITERIA) + f" | {r['judge_mean']} | {r['judge_critical']} |"
        )

    lines += ["", "## По персонам (средняя оценка судьи · исход)", ""]
    lines.append("| Персона | " + " | ".join(configs) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in configs) + " |")
    for persona in dict.fromkeys(item.persona for item in dialogs):
        cells = []
        for config in configs:
            mine = [item for item in dialogs if item.persona == persona and item.config == config]
            if not mine:
                cells.append("-")
                continue
            scores = [value for value in (mean_score(item.judge) for item in mine if "scores" in item.judge) if value is not None]
            ends = ", ".join(("📞" if item.checks["phone_saved"] else "") + item.end for item in mine)
            cells.append(f"{_avg(scores)} · {ends}")
        lines.append(f"| {persona} | " + " | ".join(cells) + " |")

    lines += ["", f"## Худшие диалоги ({WORST_SHOWN})", ""]
    for dialog in sorted(dialogs, key=_badness)[:WORST_SHOWN]:
        lines += _dialog_block(dialog)
    report = "\n".join(lines)
    (out / "report.md").write_text(report, encoding="utf-8")
    (out / "results.json").write_text(
        json.dumps({"meta": meta, "summary": rows, "dialogs": [asdict(item) for item in dialogs]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _dialog_block(dialog: Dialog) -> list[str]:
    checks = dialog.checks
    flags = []
    if checks.get("invented_numbers"):
        flags.append("чужие суммы: " + ", ".join(f"{item['number']} (#{item['turn']})" for item in checks["invented_numbers"]))
    if checks.get("repeated_questions"):
        flags.append(f"повторы вопросов: {len(checks['repeated_questions'])}")
    if checks.get("missing_handoff"):
        flags.append("нет нужной передачи")
    if checks.get("unwarranted_handoffs"):
        flags.append("лишняя передача: " + ", ".join(checks["unwarranted_handoffs"]))
    if checks.get("wrong_offer"):
        flags.append("не тот тип сделки в репликах " + ", ".join(map(str, checks["wrong_offer"])))
    score = mean_score(dialog.judge) if "scores" in dialog.judge else None
    lines = [
        f"### {dialog.persona} · {dialog.config} · попытка {dialog.attempt}",
        "",
        f"Итог: {dialog.end}{', телефон сохранён' if dialog.phone_saved else ''}. "
        f"Судья: {f'{score:.2f}' if score is not None else '-'}. {'; '.join(flags)}",
    ]
    if dialog.judge.get("summary"):
        lines.append(f"> Судья: {dialog.judge['summary']}")
    if dialog.judge.get("error"):
        lines.append(f"> Судья: ошибка — {dialog.judge['error']}")
    lines.append("")
    for index, turn in enumerate(dialog.turns, 1):
        lines.append(f"{index}. **Клиент:** {turn.customer}")
        marks = []
        if turn.handoff:
            marks.append(f"передача: {turn.handoff}")
        if turn.substituted:
            marks.append("подмена ядра: " + ", ".join(step for step in turn.steps if step.startswith(("grounded", "fallback", "validator", "empty"))))
        tail = f" _({'; '.join(marks)}; {turn.latency_ms} мс)_" if marks else f" _({turn.latency_ms} мс)_"
        lines.append(f"   **Plumo:** {turn.agent or '(нет ответа)'}{tail}")
    if dialog.error:
        lines.append(f"\nОшибка: {dialog.error}")
    notes = dialog.judge.get("notes") or {}
    if notes:
        lines.append("")
        for key, title in CRITERIA.items():
            if notes.get(key):
                lines.append(f"- {title} ({dialog.judge['scores'].get(key) or '-'}): {notes[key]}")
    lines.append("")
    return lines
