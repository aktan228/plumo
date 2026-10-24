"""The simulated customer. Sees only its persona card and the dialog, never the agent's prompt or data."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.dialog_eval.personas import Persona
from app.infrastructure.ai.openrouter_llm import parse_json_object

STATUSES = ("continue", "gave_contact", "declined", "left")

SIMULATOR_RULES = """Ты играешь клиента, который пишет в Telegram агентству недвижимости в Бишкеке. Ты не ассистент и не помогаешь собеседнику: ты живой человек со своими целями из карточки ниже.

Правила:
- Одно сообщение за раз, как в мессенджере: коротко и в стиле карточки (язык, длина, ошибки, «ты/вы»).
- Не выкладывай всю карточку сразу. Детали — когда спросят или к слову.
- Реагируй на то, что тебе написали. Не соглашайся быстрее и проще, чем сказано в карточке.
- Ты не знаешь, какие квартиры есть у агентства, и не придумываешь их.
- Телефон из карточки называй только когда выполнены условия карточки.
- Собеседник может оказаться ботом — это нормально, веди себя по карточке.

Ответь JSON: {"message": "текст сообщения", "status": "continue" | "gave_contact" | "declined" | "left"}
- gave_contact — в этом сообщении ты назвал свой телефон;
- declined — отказался и прощаешься;
- left — уходишь без явного отказа («ладно», «потом напишу»);
- continue — разговор продолжается."""


@dataclass(slots=True)
class CustomerLine:
    text: str
    status: str
    cost: float = 0.0


def transcript(turns: list[tuple[str, str]]) -> str:
    """(customer, agent) pairs as the customer reads them."""

    lines = []
    for customer, agent in turns:
        lines.append(f"Ты: {customer}")
        lines.append(f"Агентство: {agent}")
    return "\n".join(lines)


class MockSimulator:
    """Plays the persona's scripted lines; no network."""

    async def next(self, persona: Persona, turns: list[tuple[str, str]]) -> CustomerLine:
        index = len(turns)
        lines = persona.mock_lines
        if index >= len(lines):
            return CustomerLine("", "left")
        text = lines[index]
        if index < len(lines) - 1:
            return CustomerLine(text, "continue")
        return CustomerLine(text, "gave_contact" if re.search(r"\d{3}\s?\d{3}", text) else "left")

    async def aclose(self) -> None:
        return None


class ModelSimulator:
    """A cheap model plays the customer through the OpenRouter adapter (retries, real cost)."""

    def __init__(self, model: str) -> None:
        from app.infrastructure.ai.openrouter_llm import OpenRouterLLMProvider

        # Thinking off: the customer's line is short and the cheap model is slower with it.
        self.provider = OpenRouterLLMProvider(
            "dialog_eval_customer", model, extra_body={"reasoning": {"effort": "none"}}, max_tokens=300
        )

    async def next(self, persona: Persona, turns: list[tuple[str, str]]) -> CustomerLine:
        prompt = (
            f"Переписка до сих пор:\n{transcript(turns)}\n\n"
            "Напиши следующее сообщение клиента. Только JSON."
        )
        payload = await self.provider.chat(
            [
                {"role": "system", "content": f"{SIMULATOR_RULES}\n\n# Карточка персонажа\n{persona.card}\nТелефон: {persona.phone}"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
        )
        parsed = parse_json_object(payload["text"]) or {}
        text = str(parsed.get("message") or "").strip()
        status = str(parsed.get("status") or "continue")
        if status not in STATUSES:
            status = "continue"
        return CustomerLine(text, status if text else "left", float(payload["usage"]["estimated_cost"]))

    async def aclose(self) -> None:
        await self.provider.aclose()
