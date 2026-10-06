from app.infrastructure.ai.openrouter_llm import parse_generation_json, parse_json_object


def test_parse_json_object_from_fence() -> None:
    raw = 'prefix\n```json\n{"label": "greeting", "confidence": 0.9}\n```\n'
    parsed = parse_json_object(raw)
    assert parsed == {"label": "greeting", "confidence": 0.9}


def test_parse_generation_falls_back_to_plain_text() -> None:
    parsed = parse_generation_json("Здравствуйте!")
    assert parsed["text"] == "Здравствуйте!"
    assert parsed["actions"] == []
