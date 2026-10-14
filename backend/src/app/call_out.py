"""One test call from the agent to a phone, through the Twilio number imported into ElevenLabs.

    python -m app.call_out --to +996555123456 [--business-name "Цветочная База"] [--dry-run]

A manual tool for demos and tests: one number per run, typed by a person. It is
not autodialing (out of the MVP). On an outbound call the platform's "caller" is
our own Twilio number, so the dialled number is sent as the customer: otherwise
every person the agent calls would land in one customer card.

Needs in backend/.env: ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID and, if the
account has several numbers, ELEVENLABS_PHONE_NUMBER_ID.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

import httpx

import app.config  # noqa: F401  loads backend/.env
from app.domain.phrases import DEFAULT_ASSISTANT_NAME

API = "https://api.elevenlabs.io"
_E164 = re.compile(r"\+\d{10,15}")


def outbound_greeting(business_name: str, assistant_name: str = DEFAULT_ASSISTANT_NAME) -> str:
    # The AI and the recording are disclosed in the first words, as on inbound calls.
    return (
        f"Здравствуйте! Это {assistant_name}, ИИ-ассистент компании «{business_name}». "
        "Разговор записывается. Удобно сейчас поговорить пару минут?"
    )


def call_payload(*, agent_id: str, phone_number_id: str, to_number: str, business_name: str) -> dict[str, Any]:
    if not _E164.fullmatch(to_number):
        raise ValueError("номер нужен в формате +996555123456")
    return {
        "agent_id": agent_id,
        "agent_phone_number_id": phone_number_id,
        "to_number": to_number,
        "conversation_initiation_client_data": {
            # Read by parse_llm_request before the prompt markers: the customer is
            # the person we call, not our own number.
            "custom_llm_extra_body": {"caller_id": to_number},
            "dynamic_variables": {"plumo_customer_phone": to_number},
            "conversation_config_override": {
                "agent": {"first_message": outbound_greeting(business_name), "language": "ru"}
            },
        },
    }


def _phone_number_id(client: httpx.Client) -> str | None:
    configured = os.getenv("ELEVENLABS_PHONE_NUMBER_ID", "").strip()
    if configured:
        return configured
    numbers = client.get("/v1/convai/phone-numbers").json()
    numbers = numbers if isinstance(numbers, list) else numbers.get("phone_numbers", [])
    if len(numbers) == 1:
        return numbers[0].get("phone_number_id")
    print("Номеров в ElevenLabs: %d. Укажите нужный в ELEVENLABS_PHONE_NUMBER_ID:" % len(numbers))
    for item in numbers:
        print(f"  {item.get('phone_number_id')}  {item.get('phone_number')}  {item.get('provider')}  {item.get('label')}")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Тестовый исходящий звонок агента на один номер")
    parser.add_argument("--to", required=True, help="номер в формате +996555123456")
    parser.add_argument("--business-name", default="Цветочная База", help="имя компании в приветствии")
    parser.add_argument("--dry-run", action="store_true", help="показать запрос, не звонить")
    args = parser.parse_args(argv)

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    agent_id = os.getenv("ELEVENLABS_AGENT_ID", "").strip()
    if not api_key or not agent_id:
        print("Нужны ELEVENLABS_API_KEY и ELEVENLABS_AGENT_ID в backend/.env")
        return 1
    with httpx.Client(base_url=API, headers={"xi-api-key": api_key}, timeout=30) as client:
        phone_number_id = os.getenv("ELEVENLABS_PHONE_NUMBER_ID", "").strip() or (
            "<id номера>" if args.dry_run else _phone_number_id(client)
        )
        if not phone_number_id:
            return 1
        try:
            payload = call_payload(
                agent_id=agent_id, phone_number_id=phone_number_id, to_number=args.to, business_name=args.business_name
            )
        except ValueError as exc:
            print(exc)
            return 1
        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        response = client.post("/v1/convai/twilio/outbound-call", json=payload)
    if response.status_code >= 400:
        print(f"ElevenLabs ответил {response.status_code}: {response.text[:500]}")
        return 1
    result = response.json()
    print(f"звоним: success={result.get('success')} conversation_id={result.get('conversation_id')} {result.get('message') or ''}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
