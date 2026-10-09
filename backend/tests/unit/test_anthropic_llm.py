"""Claude adapter on a fake SDK client: request shape, thinking per model, refusals, cost. No network."""

import json
from types import SimpleNamespace

import pytest

from app.domain.errors import ProviderTransientError
from app.domain.models import RouteDecision
from app.infrastructure.ai.anthropic_llm import AnthropicLLMProvider, cost_of, thinking_for
from tests.unit.test_rules import _context

_REPLY = {
    "text": "Да, ещё продаётся. Когда удобно посмотреть?",
    "actions": [{"type": "schedule_meeting", "payload": {"date": "2026-10-10", "time": None}}],
    "handoff_required": False,
    "handoff_reason": None,
    "confidence": 0.9,
    "memory": "Интересуется Чуй.",
    "need": None,
}


class _Messages:
    def __init__(self, response) -> None:
        self.response = response
        self.seen: dict = {}

    async def create(self, **kwargs):
        self.seen = kwargs
        return self.response


def _response(payload: dict | None = None, stop: str = "end_turn", **usage):
    text = json.dumps(payload or _REPLY, ensure_ascii=False)
    numbers = {"input_tokens": 400, "output_tokens": 60, "cache_read_input_tokens": 1200, "cache_creation_input_tokens": 0}
    numbers.update(usage)
    return SimpleNamespace(
        stop_reason=stop,
        stop_details=SimpleNamespace(category="general_harms") if stop == "refusal" else None,
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(**numbers),
    )


def _provider(model: str, response) -> tuple[AnthropicLLMProvider, _Messages]:
    messages = _Messages(response)
    client = SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages))
    return AnthropicLLMProvider("anthropic_big", model, client=client), messages


async def test_request_shape_and_parsed_reply() -> None:
    provider, messages = _provider("claude-haiku-5-5", _response())
    generation = await provider.generate_response(_context("Ещё продаётся?"), RouteDecision("big", "t", 1.0))

    seen = messages.seen
    assert seen["model"] == "claude-haiku-5-5"
    assert seen["thinking"] == {"type": "disabled"}
    assert seen["output_config"]["effort"] == "low"
    assert seen["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in seen
    assert seen["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Объекты и факты" in seen["system"][1]["text"]
    assert seen["messages"] == [{"role": "user", "content": "Ещё продаётся?"}]

    assert generation.text.startswith("Да, ещё продаётся")
    assert generation.actions[0].payload == {"date": "2026-10-10"}
    assert generation.model_used == "anthropic_big:claude-haiku-5-5"
    assert generation.input_tokens == 1600
    assert generation.estimated_cost == pytest.approx((400 * 0.10 + 1200 * 0.01 + 60 * 0.50) / 1_000_000)


def test_thinking_off_in_the_form_each_model_accepts() -> None:
    assert thinking_for("claude-sonnet-5-5") == {"type": "between_tools"}
    assert thinking_for("claude-haiku-5-5") == {"type": "disabled"}
    assert thinking_for("claude-opus-5-5") == {"type": "adaptive"}


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
async def test_refusal_and_cut_off_are_transient_not_sent(stop: str) -> None:
    provider, _ = _provider("claude-sonnet-5-5", _response(stop=stop))
    with pytest.raises(ProviderTransientError):
        await provider.generate_response(_context("привет"), RouteDecision("big", "t", 1.0))


def test_cache_write_costs_more_than_a_read() -> None:
    written = cost_of("claude-sonnet-5-5", SimpleNamespace(input_tokens=0, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=1000))
    read = cost_of("claude-sonnet-5-5", SimpleNamespace(input_tokens=0, output_tokens=0, cache_read_input_tokens=1000, cache_creation_input_tokens=0))
    assert written == pytest.approx(1000 * 2.0 * 1.25 / 1_000_000)
    assert read == pytest.approx(1000 * 0.20 / 1_000_000)
