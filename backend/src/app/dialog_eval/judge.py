"""The judge grades a whole dialog by the rubric. It does not know which configuration answered."""

from __future__ import annotations

from typing import Any

from app.dialog_eval.personas import Persona
from app.dialog_eval.runner import Dialog
from app.infrastructure.ai.openrouter_llm import parse_json_object

CRITERIA: dict[str, str] = {
    "liveliness": "Живость",
    "brevity": "Краткость",
    "listening": "Слушает клиента",
    "matching": "Подбор",
    "objections": "Возражения",
    "next_step": "Доведение до шага",
    "honesty": "Честность",
}

JUDGE_RULES = """Ты оцениваешь переписку ИИ-ассистента агентства недвижимости Demo Realty (Бишкек) с клиентом в Telegram.

Задача ассистента: звучать как внимательный живой менеджер, выяснить потребность, подобрать вариант из данных агентства, объяснить, почему он подходит, работать с возражениями без давления и довести до следующего шага — просмотра или контакта для менеджера. Сделку, торг и скидки ведёт живой менеджер.
Правила ассистента: цены, наличие, условия оплаты и сроки — только из данных агентства ниже; если факта нет — честно сказать и передать менеджеру. Не обещать скидку, бронь, звонок «через 5 минут» или соединение. Отвечать на языке клиента (русский, кыргызский или смесь). Первая реплика по закону содержит представление «ИИ-ассистент» — это не минус само по себе, минус только если оно тяжеловесное.

Оцени ВЕСЬ диалог по каждому критерию от 1 до 5:
- liveliness (живость): 5 — реагирует на конкретные слова клиента, звучит как человек; 3 — в целом нормально, но местами шаблонно; 1 — система: канцелярит, одинаковые заготовки, поправки по ходу, «я ИИ, не могу».
- brevity (краткость): 5 — по делу, длина под собеседника; 3 — иногда лишнее; 1 — простыни текста, списки там, где хватило бы фразы.
- listening (слушает клиента): 5 — помнит сказанное, не переспрашивает, опирается на слова клиента; 3 — один повтор или пропущенная деталь; 1 — переспрашивает известное, игнорирует ответы.
- matching (подбор): 5 — конкретный вариант под потребность и бюджет и «почему вам»; 3 — вариант назван, но без связи с потребностью; 1 — не подобрал, неверный тип сделки (аренда покупателю), вариант вне бюджета без объяснения.
- objections (возражения): 5 — признаёт, объясняет ценность из данных, предлагает альтернативу, без давления; 3 — отвечает формально; 1 — спорит, давит, сдаётся или обещает скидку. null — если возражений не было.
- next_step (доведение до шага): 5 — вовремя и уверенно предлагает просмотр с выбором, просит контакт естественно; 3 — предлагает шаг поздно или вяло; 1 — шага нет или давит раньше времени.
- honesty (честность): 5 — все факты из данных, честно говорит, чего не знает; 3 — неточность без вреда; 1 — выдуманный факт, обещание вне правил, ложное «записал» или «соединяю».

critical_error = true, если хоть одна реплика могла навредить клиенту или бизнесу: выдуманный факт, обещание скидки или брони, грубость, ложное «записал/соединяю».
worst_turn — номер худшей реплики ассистента (или null), summary — 1–2 предложения: главное, что хорошо и что плохо.
К каждой оценке — note: одно короткое предложение с цитатой или номером реплики. Цитаты только в «ёлочках», без двойных кавычек внутри строк JSON.

Ответь только JSON:
{"scores": {"liveliness": {"score": 1-5, "note": "..."}, "brevity": {...}, "listening": {...}, "matching": {...}, "objections": {"score": 1-5 или null, "note": "..."}, "next_step": {...}, "honesty": {...}}, "critical_error": false, "worst_turn": 3, "summary": "..."}"""


_SCORE = {
    "type": "object",
    "properties": {"score": {"anyOf": [{"type": "integer"}, {"type": "null"}]}, "note": {"type": "string"}},
    "required": ["score", "note"],
    "additionalProperties": False,
}
# Structured output: in plain JSON mode the judge quoted the agent with raw double quotes
# and broke the JSON in 3 of 10 verdicts, whatever the prompt said.
VERDICT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "object",
                    "properties": dict.fromkeys(CRITERIA, _SCORE),
                    "required": list(CRITERIA),
                    "additionalProperties": False,
                },
                "critical_error": {"type": "boolean"},
                "worst_turn": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "summary": {"type": "string"},
            },
            "required": ["scores", "critical_error", "worst_turn", "summary"],
            "additionalProperties": False,
        },
    },
}


def judge_prompt(dialog: Dialog, persona: Persona) -> str:
    lines = []
    for index, turn in enumerate(dialog.turns, 1):
        lines.append(f"[{index}] Клиент: {turn.customer}")
        mark = f" [создана передача менеджеру: {turn.handoff}]" if turn.handoff else ""
        lines.append(f"[{index}] Ассистент: {turn.agent or '(не ответил)'}{mark}")
    ending = {
        "gave_contact": "клиент оставил телефон",
        "declined": "клиент отказался",
        "left": "клиент ушёл",
        "turn_limit": "закончился лимит реплик",
        "error": f"ошибка: {dialog.error}",
    }.get(dialog.end, dialog.end)
    return (
        f"# Клиент (карточка, ассистент её не видел)\n{persona.card}\n\n"
        f"# Переписка\n" + "\n".join(lines) + f"\n\nИтог: {ending}."
    )


def parse_verdict(raw: str) -> dict[str, Any]:
    data = parse_json_object(raw) or {}
    scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
    result: dict[str, Any] = {"scores": {}, "notes": {}}
    for key in CRITERIA:
        item = scores.get(key) if isinstance(scores.get(key), dict) else {}
        score = item.get("score")
        result["scores"][key] = score if isinstance(score, int) and 1 <= score <= 5 else None
        result["notes"][key] = str(item.get("note") or "")
    if not any(value is not None for value in result["scores"].values()):
        return {"error": "judge returned no scores"}
    result["critical_error"] = bool(data.get("critical_error"))
    worst = data.get("worst_turn")
    result["worst_turn"] = worst if isinstance(worst, int) else None
    result["summary"] = str(data.get("summary") or "")
    return result


def mean_score(verdict: dict[str, Any]) -> float | None:
    values = [value for value in (verdict.get("scores") or {}).values() if value is not None]
    return sum(values) / len(values) if values else None


class MockJudge:
    cost = 0.0

    async def grade(self, dialog: Dialog, persona: Persona) -> None:
        score = 2 if dialog.checks.get("critical") else 4
        dialog.judge = {
            "scores": dict.fromkeys(CRITERIA, score),
            "notes": dict.fromkeys(CRITERIA, "mock"),
            "critical_error": bool(dialog.checks.get("critical")),
            "worst_turn": None,
            "summary": "mock",
        }

    async def aclose(self) -> None:
        return None


class ModelJudge:
    def __init__(self, model: str, catalog: str) -> None:
        from app.infrastructure.ai.openrouter_llm import OpenRouterLLMProvider

        # Sonnet 5.5 on OpenRouter cannot turn reasoning off ("Reasoning is mandatory", HTTP 400 on
        # 2026-10-24): low is the cheapest. Temperature 0: the same dialog gets the same grade more often.
        self.provider = OpenRouterLLMProvider(
            "dialog_eval_judge", model, extra_body={"reasoning": {"effort": "low"}, "response_format": VERDICT_SCHEMA},
            max_tokens=4000, timeout_s=120,
            # A verdict is not latency-bound: ride out a 429 burst instead of losing the grade.
            max_retries=6, backoff_s=1.0,
        )
        self.system = [
            # Same rules and catalog in every call: Anthropic caches them through OpenRouter.
            {"type": "text", "text": f"{JUDGE_RULES}\n\n{catalog}", "cache_control": {"type": "ephemeral"}}
        ]
        self.cost = 0.0

    async def grade(self, dialog: Dialog, persona: Persona) -> None:
        try:
            payload = await self.provider.chat(
                [{"role": "system", "content": self.system}, {"role": "user", "content": judge_prompt(dialog, persona)}],
                temperature=0,
            )
        except Exception as exc:  # one failed verdict must not drop the whole run
            dialog.judge = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            return
        self.cost += float(payload["usage"]["estimated_cost"])
        dialog.judge = parse_verdict(payload["text"])
        if "error" in dialog.judge:
            dialog.judge["raw"] = payload["text"][:500]

    async def aclose(self) -> None:
        await self.provider.aclose()
