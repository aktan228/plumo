"""ElevenLabs agent config built by the setup script. No network."""

from app.elevenlabs_setup import PROMPT_MARKERS, agent_payload, endpoints, set_env_values
from app.infrastructure.telephony.elevenlabs import parse_llm_request


def test_agent_points_every_callback_at_plumo() -> None:
    payload = agent_payload(
        public_url="https://plumo.example.org/",
        llm_token="tok",
        llm_secret_id="sec_1",
        webhook_id="wh_1",
    )
    agent = payload["conversation_config"]["agent"]
    llm = agent["prompt"]["custom_llm"]
    assert agent["prompt"]["llm"] == "custom-llm"
    assert llm["url"] == "https://plumo.example.org/api/v1/telephony/elevenlabs/v1"
    assert llm["api_key"] == {"secret_id": "sec_1"}
    assert "ИИ-ассистент" in agent["first_message"]
    assert "записывается" in agent["first_message"]
    workspace = payload["platform_settings"]["workspace_overrides"]
    hook = workspace["conversation_initiation_client_data_webhook"]
    assert hook["url"].endswith("/telephony/elevenlabs/initiation")
    assert hook["request_headers"] == {"Authorization": "Bearer tok"}
    assert workspace["webhooks"]["post_call_webhook_id"] == "wh_1"
    assert payload["platform_settings"]["overrides"]["conversation_config_override"]["agent"] == {
        "first_message": True,
        "language": True,
    }
    # Pinned TTS model that speaks Kyrgyz; digits are read out by the platform, not the prompt.
    assert payload["conversation_config"]["tts"] == {"model_id": "eleven_v4_turbo", "text_normalisation_type": "elevenlabs"}
    assert endpoints("https://h")["post_call"] == "https://h/api/v1/telephony/elevenlabs/post-call"


def test_prompt_markers_are_what_the_core_parses() -> None:
    prompt = (
        PROMPT_MARKERS.replace("{{system__caller_id}}", "+996555111222")
        .replace("{{system__conversation_id}}", "conv_9")
        .replace("{{system__called_number}}", "+996312000002")
    )
    turn = parse_llm_request({"messages": [{"role": "system", "content": prompt}, {"role": "user", "content": "Алло"}]})
    assert (turn.caller, turn.call_id, turn.called) == ("+996555111222", "conv_9", "+996312000002")


def test_env_values_replace_and_append(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("A=1\nELEVENLABS_AGENT_ID=\n# note\n", encoding="utf-8")
    set_env_values(env, {"ELEVENLABS_AGENT_ID": "ag_1", "NEW": "x"})
    assert env.read_text(encoding="utf-8") == "A=1\nELEVENLABS_AGENT_ID=ag_1\n# note\nNEW=x\n"
