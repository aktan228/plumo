from app.infrastructure.ai.openrouter_llm import parse_generation_json, parse_json_object


def test_parse_json_object_from_fence() -> None:
    raw = 'prefix\n```json\n{"label": "greeting", "confidence": 0.9}\n```\n'
    parsed = parse_json_object(raw)
    assert parsed == {"label": "greeting", "confidence": 0.9}


def test_parse_generation_falls_back_to_plain_text() -> None:
    parsed = parse_generation_json("Здравствуйте!")
    assert parsed["text"] == "Здравствуйте!"
    assert parsed["actions"] == []


def test_parse_generation_keeps_memory_and_need() -> None:
    raw = (
        '{"text":"Есть вариант на Чуй за 85 000 USD.","actions":[],"confidence":0.8,'
        '"memory":"Ищет 2-комнатную для семьи, смотрел Чуй за 85 000 USD.","need":"2-комнатная для семьи"}'
    )
    parsed = parse_generation_json(raw)
    assert parsed["memory"].startswith("Ищет 2-комнатную")
    assert parsed["need"] == "2-комнатная для семьи"


def test_clip_drops_placeholders_and_squashes_space() -> None:
    from app.infrastructure.ai.openrouter_llm import _clip

    assert _clip("null", 50) is None
    assert _clip(None, 50) is None
    assert _clip("  две\n комнаты  ", 50) == "две комнаты"
    assert _clip("x" * 900, 500) == "x" * 500


async def test_local_provider_needs_no_key_and_costs_nothing(monkeypatch) -> None:
    import httpx

    from app.config import Settings
    from app.container import _llm_provider
    from app.domain.models import RouteDecision
    from tests.unit.test_rules import _context

    monkeypatch.delenv("LOCAL_LLM_API_KEY", raising=False)
    seen = {}

    def reply(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        body = {
            "choices": [{"message": {"content": '{"text":"Здравствуйте! Что ищете?","confidence":0.9}'}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 40},
        }
        return httpx.Response(200, json=body)

    settings = Settings(ai_mode="production", local_llm_base_url="http://gpu-box:8000/v1/chat/completions")
    provider = _llm_provider("local_small", settings)
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    generation = await provider.generate_response(_context("привет"), RouteDecision("small", "greeting", 0.9))

    assert seen == {"auth": None, "url": "http://gpu-box:8000/v1/chat/completions"}
    assert generation.text == "Здравствуйте! Что ищете?"
    assert generation.model_used == "local_small:plumo-small"
    assert (generation.input_tokens, generation.estimated_cost) == (900, 0.0)
