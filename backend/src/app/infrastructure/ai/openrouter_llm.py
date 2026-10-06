"""OpenRouter LLM adapter. AgentService never imports this module."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

from app.domain.enums import ActionType
from app.domain.errors import ProviderUnavailable
from app.domain.models import (
    Action,
    AgentContext,
    Classification,
    ExtractedCustomerData,
    LLMGeneration,
    Message,
    RouteDecision,
    SummaryDraft,
)
from app.domain.text_signals import detect_language
from app.infrastructure.ai.mock_llm import MockLLMProvider

logger = logging.getLogger("plumo.openrouter")

_ALLOWED_ACTIONS = {item.value for item in ActionType}
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_DEFAULT_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterLLMProvider:
    """Chat completions through OpenRouter. Model id is a configuration string."""

    def __init__(
        self,
        name: str,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 45.0,
        referer: str = "https://github.com/aktan228/plumo",
        title: str = "Plumo",
    ) -> None:
        self.name = name
        self.model = model
        self.api_key = (api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")).strip()
        self.base_url = (base_url or os.getenv("OPENROUTER_BASE_URL") or _DEFAULT_URL).rstrip("/")
        self.timeout_s = timeout_s
        self.referer = referer
        self.title = title
        self._local = MockLLMProvider("local_memory", "small")
        if not self.api_key:
            raise ProviderUnavailable("OPENROUTER_API_KEY is empty")

    async def complete(self, user_text: str) -> dict:
        """One-shot probe. Not used by AgentService."""

        return await self._chat(
            [
                {
                    "role": "system",
                    "content": 'Ответь JSON {"text":"..."} одним коротким предложением на русском.',
                },
                {"role": "user", "content": user_text},
            ],
            temperature=0,
        )

    async def generate_response(self, context: AgentContext, route: RouteDecision) -> LLMGeneration:
        payload = await self._chat(
            [
                {"role": "system", "content": _system_prompt(context)},
                {"role": "user", "content": _user_prompt(context, route)},
            ],
            temperature=0.2,
        )
        parsed = parse_generation_json(payload["text"])
        usage = payload["usage"]
        return LLMGeneration(
            text=parsed["text"],
            actions=_actions(parsed.get("actions")),
            handoff_required=bool(parsed.get("handoff_required")),
            handoff_reason=_optional_str(parsed.get("handoff_reason")),
            confidence=_confidence(parsed.get("confidence"), default=0.75),
            model_used=f"{self.name}:{self.model}",
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            estimated_cost=usage["estimated_cost"],
        )

    async def classify(self, text: str, labels: list[str]) -> Classification:
        if not labels:
            return Classification("other", 0.0)
        payload = await self._chat(
            [
                {
                    "role": "system",
                    "content": "Верни JSON {\"label\": \"...\", \"confidence\": 0.0}. label только из списка.",
                },
                {"role": "user", "content": f"labels={labels}\ntext={text}"},
            ],
            temperature=0,
        )
        parsed = parse_json_object(payload["text"]) or {}
        label = str(parsed.get("label") or labels[0])
        if label not in labels:
            label = labels[0]
        return Classification(label, _confidence(parsed.get("confidence"), default=0.5))

    async def summarize(self, messages: list[Message], previous: str | None) -> SummaryDraft:
        return await self._local.summarize(messages, previous)

    async def extract_customer_data(self, text: str) -> ExtractedCustomerData:
        return await self._local.extract_customer_data(text)

    async def _chat(self, messages: list[dict[str, str]], *, temperature: float) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.referer,
            "X-Title": self.title,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(self.base_url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            logger.warning("openrouter network error")
            raise ProviderUnavailable("OpenRouter is unreachable") from exc
        if response.status_code >= 400:
            logger.warning("openrouter http %s", response.status_code)
            raise ProviderUnavailable(_public_error(response.status_code, response.text))
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderUnavailable("OpenRouter returned a non-JSON body") from exc
        text = _choice_text(data)
        if not text:
            raise ProviderUnavailable("OpenRouter returned an empty reply")
        return {"text": text, "usage": _usage(data)}


def parse_generation_json(raw: str) -> dict[str, Any]:
    parsed = parse_json_object(raw)
    if parsed is None:
        return {"text": raw.strip(), "actions": [], "handoff_required": False, "confidence": 0.7}
    text = str(parsed.get("text") or parsed.get("response_text") or "").strip()
    if not text:
        text = raw.strip()
    return {
        "text": text,
        "actions": parsed.get("actions") or [],
        "handoff_required": parsed.get("handoff_required"),
        "handoff_reason": parsed.get("handoff_reason"),
        "confidence": parsed.get("confidence"),
    }


def parse_json_object(raw: str) -> dict[str, Any] | None:
    blob = raw.strip()
    fenced = _JSON_FENCE.search(blob)
    if fenced:
        blob = fenced.group(1).strip()
    try:
        value = json.loads(blob)
    except json.JSONDecodeError:
        start = blob.find("{")
        end = blob.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(blob[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _system_prompt(context: AgentContext) -> str:
    knowledge_lines = [
        f"- {hit.item.title} [{hit.item.category}]: {hit.item.content}" for hit in context.knowledge
    ]
    knowledge = "\n".join(knowledge_lines) if knowledge_lines else "(пусто)"
    contacts = json.dumps(context.business.contacts, ensure_ascii=False)
    summary = context.summary.summary if context.summary else "-"
    facts = ", ".join(context.summary.important_facts) if context.summary else "-"
    history = "\n".join(f"{item.role}: {item.text}" for item in context.recent_messages) or "-"
    return (
        f"{context.agent_instructions}\n\n"
        f"Язык клиента: {context.language}\n"
        f"Бизнес: {context.business.name}\n"
        f"Описание: {context.business.description}\n"
        f"Часы: {context.business.working_hours}\n"
        f"Контакты: {contacts}\n"
        f"Правила: {context.business.rules}\n"
        f"База знаний:\n{knowledge}\n"
        f"Резюме клиента: {summary}\n"
        f"Факты: {facts}\n"
        f"Последние сообщения:\n{history}\n"
        "Говори как живой менеджер: понимай смысл вопроса, даже если слова не совпали с базой. "
        "Ответ только JSON: "
        '{"text":"...","actions":[],"handoff_required":false,"handoff_reason":null,"confidence":0.8}. '
        "actions.type: schedule_meeting, request_phone, handoff, update_customer. "
        "Если факта нет в базе знаний, text — отказ без выдуманных цифр и handoff_required true."
    )


def _user_prompt(context: AgentContext, route: RouteDecision) -> str:
    return f"route={route.model} reason={route.reason}\ncurrent_message={context.current_message}"


def _actions(raw: Any) -> list[Action]:
    if not isinstance(raw, list):
        return []
    actions: list[Action] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "")
        if kind not in _ALLOWED_ACTIONS:
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        actions.append(Action(kind, payload))
    return actions


def _choice_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [str(part.get("text") or "") for part in content if isinstance(part, dict)]
        return "".join(parts).strip()
    return ""


def _usage(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    cost = usage.get("cost")
    if cost is None:
        cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": float(cost),
    }


def _confidence(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _public_error(status: int, body: str) -> str:
    if status in (401, 403):
        return "OpenRouter rejected the API key"
    if status == 402:
        return "OpenRouter has no remaining credits"
    if status == 429:
        return "OpenRouter rate limit"
    return f"OpenRouter HTTP {status}"
