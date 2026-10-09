"""OpenAI-compatible chat adapter: OpenRouter, Gemini direct, DeepSeek, OpenAI.

AgentService never imports this module. A vendor is a base URL, a key and a
model id; the request and the JSON reply contract are the same for all of them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from typing import Any

import httpx

from app.domain.enums import ActionType
from app.domain.errors import ProviderTransientError, ProviderUnavailable
from app.domain.models import (
    Action,
    AgentContext,
    Classification,
    ExtractedCustomerData,
    LLMGeneration,
    Message,
    RouteDecision,
    SummaryDraft,
    utcnow,
)
from app.domain.scheduling import BUSINESS_TZ
from app.infrastructure.ai.mock_llm import MockLLMProvider

logger = logging.getLogger("plumo.openrouter")

_ALLOWED_ACTIONS = {item.value for item in ActionType}
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_DEFAULT_URL = "https://openrouter.ai/api/v1/chat/completions"
_SPEAKER = {"user": "Клиент", "assistant": "Вы", "manager": "Менеджер (живой человек)"}


# USD per 1M tokens: (input, output, cached input) for vendors that do not
# return a cost. OpenRouter returns `usage.cost` itself. Checked 2026-10-09 on
# the OpenRouter catalog, which passes Google's prices through; re-check on
# ai.google.dev/pricing before a pilot. Gemini 3.6-3.8 Flash prices double on 2027-01-01.
PRICES: dict[str, tuple[float, float, float]] = {
    "gemini-2.5-flash-lite": (0.10, 0.40, 0.01),
    "gemini-2.5-flash": (0.30, 2.50, 0.03),
    "gemini-3.1-flash-lite": (0.25, 1.50, 0.025),
    "gemini-3.5-flash-lite": (0.30, 2.50, 0.03),
    "gemini-3.5-flash": (1.50, 9.00, 0.15),
    "gemini-3.6-flash": (0.75, 3.75, 0.075),
    "gemini-3.7-flash": (0.75, 3.75, 0.075),
    "gemini-3.8-flash": (0.75, 3.75, 0.075),
    "gemini-3-flash": (0.50, 3.00, 0.05),
    "gpt-5-nano": (0.05, 0.40, 0.005),
    "gpt-5-mini": (0.25, 2.00, 0.025),
    "deepseek-chat": (0.28, 0.42, 0.028),
}
# Statuses retried with backoff. 404 and "model is gone" switch to a fallback model instead.
_RETRY_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_GONE_HINTS = ("not found", "no longer available", "deprecated", "is not supported", "does not exist", "no endpoints")


class OpenRouterLLMProvider:
    """Chat completions over any OpenAI-compatible endpoint. Defaults to OpenRouter."""

    def __init__(
        self,
        name: str,
        model: str,
        *,
        api_key: str | None = None,
        api_key_env: str = "OPENROUTER_API_KEY",
        base_url: str | None = None,
        vendor: str = "OpenRouter",
        extra_body: dict[str, Any] | None = None,
        max_tokens: int = 600,
        timeout_s: float = 45.0,
        referer: str = "https://github.com/aktan228/plumo",
        title: str = "Plumo",
        require_key: bool = True,
        price: tuple[float, float] | tuple[float, float, float] | None = None,
        fallback_models: list[str] | None = None,
        max_retries: int = 2,
        backoff_s: float = 0.4,
    ) -> None:
        self.name = name
        self.model = model
        self.vendor = vendor
        self.api_key = (api_key if api_key is not None else os.getenv(api_key_env, "")).strip()
        default_url = os.getenv("OPENROUTER_BASE_URL") if vendor == "OpenRouter" else None
        self.base_url = (base_url or default_url or _DEFAULT_URL).rstrip("/")
        self.extra_body = dict(extra_body or {})
        # Caps a chatty reply and keeps OpenRouter from reserving credit for
        # its default (huge) output limit, which fails with 402 on low balance.
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.referer = referer
        self.title = title
        # USD per 1M tokens (input, output[, cached]). None: look the model up in PRICES.
        self.price = price
        # Tried in order when the current model answers 404 or "no longer
        # available". The switch is sticky: a retired model is not retried.
        self.models = [model, *[item for item in (fallback_models or []) if item and item != model]]
        self.max_retries = max(0, max_retries)
        self.backoff_s = backoff_s
        self._local = MockLLMProvider("local_memory", "small")
        self._client: httpx.AsyncClient | None = None
        if require_key and not self.api_key:
            raise ProviderUnavailable(f"{api_key_env} is empty")

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
            temperature=0.5,
        )
        parsed = parse_generation_json(payload["text"])
        usage = payload["usage"]
        return LLMGeneration(
            text=parsed["text"],
            actions=_actions(parsed.get("actions")),
            handoff_required=bool(parsed.get("handoff_required")),
            handoff_reason=_optional_str(parsed.get("handoff_reason")),
            confidence=_confidence(parsed.get("confidence"), default=0.75),
            model_used=f"{self.name}:{payload['model']}",
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            estimated_cost=usage["estimated_cost"],
            memory=_clip(parsed.get("memory"), 500),
            need=_clip(parsed.get("need"), 120),
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
        """One reply. Transient errors are retried with backoff; a retired model falls back.

        The caller bounds the whole call with its turn budget, so retries never
        keep a caller in silence past that budget.
        """

        while True:
            model = self.models[0]
            try:
                return await self._chat_with_retries(model, messages, temperature)
            except _ModelGone:
                if len(self.models) == 1:
                    raise ProviderUnavailable(f"{self.vendor} model {model} is no longer available") from None
                self.models.pop(0)
                self.model = self.models[0]
                logger.error("llm model retired, switching", extra={"vendor": self.vendor, "from": model, "to": self.model})

    async def _chat_with_retries(self, model: str, messages: list[dict[str, str]], temperature: float) -> dict[str, Any]:
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            # Every Plumo prompt asks for one JSON object; JSON mode makes the
            # free and small models stop wrapping it in prose.
            "response_format": {"type": "json_object"},
            **self.extra_body,
        }
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": self.referer,
            "X-Title": self.title,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        attempt = 0
        while True:
            try:
                response = await self._http().post(self.base_url, headers=headers, json=body)
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    attempt += 1
                    await asyncio.sleep(self._delay(attempt, None))
                    continue
                logger.warning("llm network error", extra={"vendor": self.vendor})
                raise ProviderTransientError(f"{self.vendor} is unreachable") from exc
            status = response.status_code
            if status in _RETRY_STATUSES and attempt < self.max_retries:
                attempt += 1
                logger.warning("llm http %s, retry %s", status, attempt, extra={"vendor": self.vendor})
                await asyncio.sleep(self._delay(attempt, response.headers.get("retry-after")))
                continue
            if status >= 400:
                logger.warning("llm http %s", status, extra={"vendor": self.vendor})
                if _model_gone(status, response.text):
                    raise _ModelGone(model)
                error = ProviderTransientError if status in _RETRY_STATUSES or status >= 500 else ProviderUnavailable
                raise error(_public_error(self.vendor, status))
            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                raise ProviderTransientError(f"{self.vendor} returned a non-JSON body") from exc
            text = _choice_text(data)
            if not text:
                raise ProviderTransientError(f"{self.vendor} returned an empty reply")
            return {"text": text, "usage": _usage(data, model, self.price), "model": model}

    def _delay(self, attempt: int, retry_after: str | None) -> float:
        """Exponential backoff with jitter; a short Retry-After is honoured, a long one is capped."""

        try:
            hinted = float(retry_after) if retry_after else 0.0
        except ValueError:
            hinted = 0.0
        base = self.backoff_s * (2 ** (attempt - 1))
        return min(max(hinted, base) + random.uniform(0, self.backoff_s / 2), 3.0)

    def _http(self) -> httpx.AsyncClient:
        """One pooled client per provider. A fresh TLS handshake per turn costs voice latency."""

        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def parse_generation_json(raw: str) -> dict[str, Any]:
    parsed = parse_json_object(raw)
    if parsed is None:
        stripped = raw.strip()
        if stripped.startswith("{") or '"text"' in stripped:
            # Cut-off JSON: keep whole sentences of "text", never show braces.
            return {"text": salvage_text(stripped), "actions": [], "handoff_required": False, "confidence": 0.5}
        return {"text": stripped, "actions": [], "handoff_required": False, "confidence": 0.7}
    # A JSON reply without text must stay empty: the core then uses a grounded
    # fallback. Echoing `raw` here would send the JSON itself to the customer.
    text = str(parsed.get("text") or parsed.get("response_text") or "").strip()
    return {
        "text": text,
        "actions": parsed.get("actions") or [],
        "handoff_required": parsed.get("handoff_required"),
        "handoff_reason": parsed.get("handoff_reason"),
        "confidence": parsed.get("confidence"),
        "memory": parsed.get("memory"),
        "need": parsed.get("need"),
    }


def salvage_text(raw: str) -> str:
    """Complete sentences from an unterminated `"text": "..."`, or empty."""

    match = re.search(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)', raw)
    if not match:
        return ""
    try:
        text = json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        text = match.group(1)
    end = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
    return text[: end + 1].strip() if end >= 0 else ""


def _now_line() -> str:
    now = utcnow().astimezone(BUSINESS_TZ)
    days = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
    return f"{days[now.weekday()]}, {now:%Y-%m-%d %H:%M}"


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
    stable, turn = system_parts(context)
    return f"{stable}\n{turn}"


def system_parts(context: AgentContext) -> tuple[str, str]:
    """(stable, per-turn) halves of the system prompt, joined by one newline.

    The stable half is identical for every turn of a business, so providers
    with explicit cache markers (Anthropic) cache it; Gemini caches the same
    prefix implicitly.
    """

    knowledge_lines = [
        f"- {hit.item.title} [{hit.item.category}]: {hit.item.content}" for hit in context.knowledge
    ]
    knowledge = "\n".join(knowledge_lines) if knowledge_lines else "(ничего подходящего)"
    contacts = {key: value for key, value in (context.business.contacts or {}).items() if key != "assistant_name"}
    summary = context.summary.summary if context.summary else "новый клиент, раньше не общались"
    facts = [fact for fact in (context.summary.important_facts if context.summary else []) if not fact.startswith("unclear_count:")]
    known = []
    if context.customer.need:
        known.append(f"цель: {context.customer.need}")
    if context.customer.phone or context.customer.contact_phone:
        known.append("телефон уже есть, не спрашивай")
    history = "\n".join(
        f"{_SPEAKER.get(item.role, 'Вы')}: {item.text}" for item in context.recent_messages
    ) or "(это первое сообщение — поздоровайся коротко)"
    # Stable part first: instructions, answer format and the business card are
    # the same for every turn of a business, so Gemini's implicit cache bills
    # them at the cached rate. Retrieved facts, the customer and the dialog vary
    # per turn and go last.
    stable = (
        f"{context.agent_instructions}\n\n"
        "# Формат ответа\n"
        "Только JSON без пояснений: "
        '{"text":"...","actions":[],"handoff_required":false,"handoff_reason":null,"confidence":0.8,'
        '"memory":"...","need":"..."}\n'
        "text — ровно то, что прочитает или услышит клиент.\n"
        "actions.type: schedule_meeting (payload: date YYYY-MM-DD, time HH:MM), request_phone, handoff, update_customer.\n"
        "confidence — насколько ответ опирается на данные: ниже 0.6, если сомневаешься.\n"
        "memory — заметка для себя на следующий разговор, 1–2 предложения: что клиент ищет, "
        "какие объекты обсуждали, о чём договорились, что осталось открытым. Обнови «Что помним», "
        "не теряя важного. Только то, что сказал клиент или есть в данных, без догадок.\n"
        "need — потребность клиента в 2–6 словах (например «2-комнатная для семьи, до 90 000 USD») или null.\n\n"
        "# Данные агентства\n"
        f"Описание: {context.business.description}\n"
        f"Часы: {context.business.working_hours}\n"
        f"Контакты: {json.dumps(contacts, ensure_ascii=False, sort_keys=True)}\n"
        f"Правила бизнеса: {context.business.rules}\n"
        "Объекты со статусом «продана» или «не предлагать» не предлагай. "
        "Служебные пометки вроде «Статус: …» клиенту не цитируй.\n"
        "Если просят совет, вариант дешевле или на сколько человек — выбери подходящие объекты отсюда и назови цену. "
        "Если подходящие объекты есть, не отправляй к менеджеру."
    )
    turn = (
        f"Объекты и факты:\n{knowledge}\n\n"
        "# Клиент\n"
        f"Сейчас: {_now_line()} (Бишкек). Дни недели считай от этой даты.\n"
        f"Язык: {context.language}\n"
        f"Что помним: {summary}\n"
        f"Уже знаем: {', '.join(known + facts) or '-'}\n\n"
        f"# Переписка\n{history}"
    )
    return stable, turn


def _user_prompt(context: AgentContext, route: RouteDecision) -> str:
    # Only the customer's words. Routing internals are not the model's business
    # and make replies sound like a ticket system.
    del route
    return context.current_message


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


def _usage(data: dict[str, Any], model: str = "", price: tuple[float, ...] | None = None) -> dict[str, Any]:
    usage = data.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    details = usage.get("prompt_tokens_details")
    cached = min(int(details.get("cached_tokens") or 0), input_tokens) if isinstance(details, dict) else 0
    cost = usage.get("cost")
    if cost is None:
        price_in, price_out, price_cached = _three(price if price is not None else price_for(model))
        cost = ((input_tokens - cached) * price_in + cached * price_cached + output_tokens * price_out) / 1_000_000
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached,
        "estimated_cost": float(cost),
    }


def _three(price: tuple[float, ...]) -> tuple[float, float, float]:
    """(input, output) means no cache discount is known: cached input costs full price."""

    return (price[0], price[1], price[2] if len(price) > 2 else price[0])


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


def _clip(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text or text.lower() in ("null", "none", "-"):
        return None
    return text[:limit]


def price_for(model: str) -> tuple[float, float, float]:
    """Longest matching price key wins: "gemini-2.5-flash-lite" before "gemini-2.5-flash"."""

    bare = model.rsplit("/", 1)[-1]
    for key in sorted(PRICES, key=len, reverse=True):
        if bare.startswith(key):
            return PRICES[key]
    # Unknown model: assume the dearest current Flash so the cost is not understated.
    return (0.75, 3.75, 0.075)


def _model_gone(status: int, body: str) -> bool:
    if status == 404:
        return True
    if status in (400, 410):
        lowered = body.lower()
        return "model" in lowered and any(hint in lowered for hint in _GONE_HINTS)
    return False


class _ModelGone(Exception):
    pass


def _public_error(vendor: str, status: int) -> str:
    if status in (401, 403):
        return f"{vendor} rejected the API key"
    if status == 402:
        return f"{vendor} has no remaining credits"
    if status == 429:
        return f"{vendor} rate limit"
    return f"{vendor} HTTP {status}"
