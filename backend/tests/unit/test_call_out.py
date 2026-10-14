"""Outbound test call payload. No network."""

import pytest

from app.call_out import call_payload
from app.infrastructure.telephony.elevenlabs import parse_llm_request


def test_dialled_number_is_the_customer_not_our_twilio_number() -> None:
    payload = call_payload(agent_id="ag", phone_number_id="ph", to_number="+996555123456", business_name="Цветочная База")
    client = payload["conversation_initiation_client_data"]
    first = client["conversation_config_override"]["agent"]["first_message"]
    assert "ИИ-ассистент" in first and "записывается" in first and "Цветочная База" in first
    # What the Custom LLM then receives: our number in the markers, the customer in the extra body.
    turn = parse_llm_request(
        {
            "messages": [
                {"role": "system", "content": "plumo_caller=+15550001111 plumo_call=conv_1"},
                {"role": "user", "content": "Алло"},
            ],
            "elevenlabs_extra_body": client["custom_llm_extra_body"],
        }
    )
    assert turn.caller == "+996555123456"


def test_number_must_be_e164() -> None:
    with pytest.raises(ValueError):
        call_payload(agent_id="ag", phone_number_id="ph", to_number="0555123456", business_name="X")
