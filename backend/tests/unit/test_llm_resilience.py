"""LLM adapter: retries, retired-model fallback, thinking limits, cached pricing. No network."""

import httpx
import pytest

from app.config import Settings
from app.container import _llm_provider
from app.domain.errors import ProviderTransientError, ProviderUnavailable
from app.domain.models import RouteDecision
from app.infrastructure.ai.factory import AIProviderFactory
from app.infrastructure.ai.openrouter_llm import OpenRouterLLMProvider, _usage
from tests.unit.test_rules import _context

_OK = {
    "choices": [{"message": {"content": '{"text":"Да, ещё продаётся.","confidence":0.9}'}}],
    "usage": {"prompt_tokens": 1000, "completion_tokens": 50},
}


def _provider(handler, **kwargs) -> OpenRouterLLMProvider:
    provider = OpenRouterLLMProvider(
        "gemini_big",
        kwargs.pop("model", "gemini-3.8-flash"),
        api_key="k",
        base_url="https://llm.test/v1/chat/completions",
        vendor="Gemini",
        backoff_s=0.0,
        **kwargs,
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return provider


async def _ask(provider: OpenRouterLLMProvider):
    return await provider.generate_response(_context("ещё продаётся?"), RouteDecision("big", "test", 0.9))


async def test_rate_limit_is_retried_then_answered() -> None:
    seen = []

    def reply(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(429 if len(seen) < 3 else 200, json=_OK)

    generation = await _ask(_provider(reply, max_retries=2))
    assert len(seen) == 3
    assert generation.text == "Да, ещё продаётся."


async def test_retries_are_bounded() -> None:
    seen = []

    def reply(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(503, json={})

    with pytest.raises(ProviderTransientError):
        await _ask(_provider(reply, max_retries=2))
    assert len(seen) == 3


async def test_retired_model_switches_to_fallback_and_stays_there() -> None:
    models = []

    def reply(request: httpx.Request) -> httpx.Response:
        import json

        model = json.loads(request.content)["model"]
        models.append(model)
        if model == "gemini-3.8-flash":
            return httpx.Response(404, json={"error": {"message": "models/gemini-3.8-flash is not found"}})
        return httpx.Response(200, json=_OK)

    provider = _provider(reply, fallback_models=["gemini-3.7-flash"])
    first = await _ask(provider)
    second = await _ask(provider)
    assert models == ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.7-flash"]
    assert first.model_used == second.model_used == "gemini_big:gemini-3.7-flash"


async def test_model_no_longer_available_in_a_400_also_falls_back() -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        import json

        if json.loads(request.content)["model"] == "gemini-2.5-flash":
            return httpx.Response(400, json={"error": {"message": "This model is no longer available to new users."}})
        return httpx.Response(200, json=_OK)

    generation = await _ask(_provider(reply, model="gemini-2.5-flash", fallback_models=["gemini-3.1-flash-lite"]))
    assert generation.model_used.endswith("gemini-3.1-flash-lite")


async def test_every_model_gone_is_unavailable_not_transient() -> None:
    provider = _provider(lambda request: httpx.Response(404, json={}), fallback_models=["gemini-3.7-flash"])
    with pytest.raises(ProviderUnavailable):
        await _ask(provider)


async def test_bad_key_is_not_retried() -> None:
    seen = []

    def reply(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(401, json={})

    with pytest.raises(ProviderUnavailable):
        await _ask(_provider(reply))
    assert len(seen) == 1


def test_cached_tokens_are_billed_at_the_cache_rate() -> None:
    data = {"usage": {"prompt_tokens": 2000, "completion_tokens": 100, "prompt_tokens_details": {"cached_tokens": 1500}}}
    usage = _usage(data, "gemini-3.8-flash")
    expected = (500 * 0.75 + 1500 * 0.075 + 100 * 3.75) / 1_000_000
    assert usage["cached_tokens"] == 1500
    assert usage["estimated_cost"] == pytest.approx(expected)


def test_thinking_is_minimal_on_gemini_3_and_off_on_2_5(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    gemini3 = _llm_provider("gemini_big", Settings(gemini_big_model="gemini-3.8-flash"))
    gemini25 = _llm_provider("gemini_big", Settings(gemini_big_model="gemini-2.5-flash"))
    routed = _llm_provider("openrouter_big", Settings(openrouter_big_model="google/gemini-3.8-flash"))
    forced = _llm_provider("gemini_big", Settings(gemini_big_model="gemini-3.8-flash", llm_reasoning_effort="low"))
    assert gemini3.extra_body == {"reasoning_effort": "minimal"}
    assert gemini25.extra_body == {"reasoning_effort": "none"}
    assert routed.extra_body == {"reasoning": {"effort": "minimal"}}
    assert forced.extra_body == {"reasoning_effort": "low"}
    assert gemini3.models == ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.1-flash-lite"]


def test_without_a_small_model_its_turns_go_to_the_big_one() -> None:
    settings = Settings(ai_mode="production", small_model_provider="mock", big_model_provider="gemini_big")
    factory = AIProviderFactory(settings)
    big = object()
    factory.register_llm("gemini_big", big)
    assert settings.small_model_enabled is False
    assert factory.llm("small") is big
    assert factory.llm("big") is big


def test_mock_mode_keeps_both_mock_tiers() -> None:
    factory = AIProviderFactory(Settings(ai_mode="mock"))
    assert factory.small_enabled is True
    assert factory.llm("small").name == "mock_small"
