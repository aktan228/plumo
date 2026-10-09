"""Claude through the official Anthropic SDK. Same prompt and JSON contract as the other adapters.

AgentService never imports this module. The reply shape is enforced with
structured outputs (`output_config.format`), so no prefill and no JSON salvage
are needed; the parsing helpers are shared with the OpenAI-compatible adapter.

Thinking: a sales reply is short, and thinking delays speech and is billed as
output. Haiku 5.5 accepts `{"type": "disabled"}` at effort high or below;
Sonnet 5.5 rejects it and turns thinking off with `{"type": "between_tools"}`.
Sampling parameters are not sent: non-default values are rejected on these models.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic

from app.domain.errors import ProviderTransientError, ProviderUnavailable
from app.domain.models import (
    AgentContext,
    Classification,
    ExtractedCustomerData,
    LLMGeneration,
    Message,
    RouteDecision,
    SummaryDraft,
)
from app.infrastructure.ai.mock_llm import MockLLMProvider
from app.infrastructure.ai.openrouter_llm import (
    _actions,
    _clip,
    _confidence,
    _optional_str,
    _user_prompt,
    system_parts,
)

logger = logging.getLogger("plumo.anthropic")

# USD per 1M tokens: (input, output, cache read). Claude API list prices, cached 2026-10-06;
# Haiku 5.5 is $0.50 / $2.50 above 100K-token prompts, which Plumo never sends.
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
}
# Cache writes cost 1.25x input for the 5-minute TTL.
_CACHE_WRITE = 1.25

# The reply contract every adapter returns. Optional fields are nullable, not omitted,
# so the schema stays strict.
REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["schedule_meeting", "request_phone", "handoff", "update_customer"],
                    },
                    "payload": {
                        "type": "object",
                        "properties": {
                            "date": {"type": ["string", "null"]},
                            "time": {"type": ["string", "null"]},
                        },
                        "required": ["date", "time"],
                        "additionalProperties": False,
                    },
                },
                "required": ["type", "payload"],
                "additionalProperties": False,
            },
        },
        "handoff_required": {"type": "boolean"},
        "handoff_reason": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "memory": {"type": ["string", "null"]},
        "need": {"type": ["string", "null"]},
    },
    "required": ["text", "actions", "handoff_required", "handoff_reason", "confidence", "memory", "need"],
    "additionalProperties": False,
}


def thinking_for(model: str) -> dict[str, str]:
    """Thinking off for a short reply, in the form each model accepts."""

    if model.startswith("claude-sonnet-5-5"):
        return {"type": "between_tools"}
    if model.startswith("claude-haiku-5-5"):
        return {"type": "disabled"}
    # Opus 5.5 cannot disable thinking; low effort keeps it short.
    return {"type": "adaptive"}


class AnthropicLLMProvider:
    """Claude Messages API. Key from ANTHROPIC_API_KEY (or an `ant auth login` profile)."""

    def __init__(
        self,
        name: str,
        model: str,
        *,
        effort: str = "low",
        max_tokens: int = 1024,
        timeout_s: float = 30.0,
        max_retries: int = 2,
        refusal_fallback: bool = False,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        # Server-side fallback re-runs a declined request on another model. It
        # is off by default here: a sales reply is not a classifier risk, and a
        # benchmark must measure the named model, not its substitute.
        self.refusal_fallback = refusal_fallback
        self._local = MockLLMProvider("local_memory", "small")
        if client is None and not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
            # A profile from `ant auth login` also works; the SDK resolves it itself.
            logger.info("ANTHROPIC_API_KEY is empty, relying on the SDK credential chain")
        try:
            self.client = client or anthropic.AsyncAnthropic(timeout=timeout_s, max_retries=max_retries)
        except anthropic.AnthropicError as exc:
            raise ProviderUnavailable(f"Anthropic client: {exc}") from exc

    async def generate_response(self, context: AgentContext, route: RouteDecision) -> LLMGeneration:
        stable, turn = system_parts(context)
        payload = await self._create(
            system=[
                {"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": turn},
            ],
            user=_user_prompt(context, route),
        )
        parsed = payload["json"]
        return LLMGeneration(
            text=str(parsed.get("text") or "").strip(),
            actions=_actions([_drop_nulls(item) for item in parsed.get("actions") or []]),
            handoff_required=bool(parsed.get("handoff_required")),
            handoff_reason=_optional_str(parsed.get("handoff_reason")),
            confidence=_confidence(parsed.get("confidence"), default=0.75),
            model_used=f"{self.name}:{self.model}",
            input_tokens=payload["input_tokens"],
            output_tokens=payload["output_tokens"],
            estimated_cost=payload["cost"],
            memory=_clip(parsed.get("memory"), 500),
            need=_clip(parsed.get("need"), 120),
        )

    async def classify(self, text: str, labels: list[str]) -> Classification:
        return Classification(labels[0], 0.0) if labels else Classification("other", 0.0)

    async def summarize(self, messages: list[Message], previous: str | None) -> SummaryDraft:
        return await self._local.summarize(messages, previous)

    async def extract_customer_data(self, text: str) -> ExtractedCustomerData:
        return await self._local.extract_customer_data(text)

    async def _create(self, *, system: list[dict], user: str) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "thinking": thinking_for(self.model),
            "output_config": {"effort": self.effort, "format": {"type": "json_schema", "schema": REPLY_SCHEMA}},
        }
        try:
            if self.refusal_fallback:
                response = await self.client.beta.messages.create(
                    **request, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                response = await self.client.messages.create(**request)
        except anthropic.AuthenticationError as exc:
            raise ProviderUnavailable("Anthropic rejected the API key") from exc
        except anthropic.PermissionDeniedError as exc:
            raise ProviderUnavailable("Anthropic key lacks access to this model") from exc
        except anthropic.NotFoundError as exc:
            raise ProviderUnavailable(f"Anthropic model {self.model} was not found") from exc
        except anthropic.BadRequestError as exc:
            raise ProviderUnavailable(f"Anthropic rejected the request: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderTransientError("Anthropic rate limit") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderTransientError(f"Anthropic HTTP {exc.status_code}") from exc
            raise ProviderUnavailable(f"Anthropic HTTP {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderTransientError("Anthropic is unreachable") from exc

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            logger.warning("anthropic_refusal", extra={"model": self.model, "category": category})
            raise ProviderTransientError(f"Anthropic declined the request ({category or 'no category'})")
        text = next((block.text for block in response.content if block.type == "text"), "")
        if response.stop_reason == "max_tokens" or not text:
            raise ProviderTransientError("Anthropic reply was cut off or empty")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderTransientError("Anthropic returned invalid JSON") from exc
        usage = response.usage
        return {
            "json": parsed if isinstance(parsed, dict) else {},
            "input_tokens": int(usage.input_tokens or 0)
            + int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            + int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
            "output_tokens": int(usage.output_tokens or 0),
            "cost": cost_of(self.model, usage),
        }

    async def aclose(self) -> None:
        await self.client.close()


def cost_of(model: str, usage: Any) -> float:
    price_in, price_out, price_cached = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    fresh = int(getattr(usage, "input_tokens", 0) or 0)
    read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    written = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    output = int(getattr(usage, "output_tokens", 0) or 0)
    return (fresh * price_in + read * price_cached + written * price_in * _CACHE_WRITE + output * price_out) / 1_000_000


def _drop_nulls(item: Any) -> Any:
    """Strict schema sends `{"date": null, "time": null}`; the core expects absent keys."""

    if not isinstance(item, dict):
        return item
    payload = {key: value for key, value in (item.get("payload") or {}).items() if value is not None}
    return {**item, "payload": payload}
