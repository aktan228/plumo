import pytest
from pydantic import ValidationError

from app.api.onboarding_schemas import AgentSettings
from app.domain.agent_settings import opening_reply, scenario_handoff, settings_prompt


@pytest.mark.parametrize("phrase,text,expected", [
    ("хочу возврат", "ХОЧУ, ВОЗВРАТ!", True), ("refund", "refunds", False),
    ("атайын суроо", "АТАЙЫН СУРОО бар", True), ("a.*b", "anything b", False),
    ("", "hello", False), ("call back", "recall back", False),
])
def test_literal_unicode_phrase_boundary(phrase, text, expected):
    assert scenario_handoff({"agent_settings": {"handoffKeywords": phrase}}, text) is expected


def test_old_published_settings_and_drafts_default_to_no_new_behavior():
    assert opening_reply({}, "Hello") == "Hello"
    assert AgentSettings().qualificationPrompt == ""
    with pytest.raises(ValidationError):
        AgentSettings(handoffKeywords="ab\n" * 11)


def test_new_scenario_fields_do_not_change_deferred_voice_prompt():
    old = {"agent_settings": {"purpose": "support", "goal": "Help customers"}}
    new = {"agent_settings": {**old["agent_settings"], "qualificationPrompt": "ask district", "openingQuestion": "Hello?", "handoffKeywords": "refund"}}
    assert settings_prompt(old, "voice") == settings_prompt(new, "voice")
    assert "ask district" in settings_prompt(new, "telegram")
