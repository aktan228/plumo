"""One dialog: the simulated customer and the whole agent core, turn by turn, as Telegram would deliver it."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app.container import Runtime, build_agent
from app.dialog_eval.personas import Persona
from app.domain.models import InboundMessage
from app.infrastructure.database.repositories import CustomerRepository
from app.seed import DEMO_BUSINESS_ID

# Steps in AgentResponse.logs where the core replaced the model's text with its own.
SUBSTITUTION_STEPS = ("grounded_fallback", "fallback:", "validator:", "empty_draft_fallback")


@dataclass(slots=True)
class Turn:
    customer: str
    agent: str = ""
    latency_ms: int = 0
    cost: float = 0.0
    model: str = ""
    route: str = ""
    handoff: str | None = None
    actions: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)

    @property
    def substituted(self) -> bool:
        return any(step.startswith(SUBSTITUTION_STEPS) for step in self.steps)


@dataclass(slots=True)
class Dialog:
    config: str
    persona: str
    attempt: int
    user_id: str
    turns: list[Turn] = field(default_factory=list)
    # gave_contact | declined | left | turn_limit | error
    end: str = "turn_limit"
    phone_saved: bool = False
    error: str | None = None
    simulator_cost: float = 0.0
    checks: dict[str, Any] = field(default_factory=dict)
    judge: dict[str, Any] = field(default_factory=dict)

    @property
    def agent_cost(self) -> float:
        return sum(turn.cost for turn in self.turns)


async def run_dialog(
    runtime: Runtime,
    config: str,
    persona: Persona,
    attempt: int,
    simulator,
    run_id: str,
    max_turns: int,
) -> Dialog:
    dialog = Dialog(config, persona.id, attempt, f"eval-{run_id}-{config}-{persona.id}-{attempt}")
    text, status = persona.opening, "continue"
    customer_id = None
    for index in range(max_turns):
        turn = Turn(text)
        dialog.turns.append(turn)
        started = time.perf_counter()
        try:
            async with runtime.session_factory() as session:
                response = await build_agent(session, runtime).process_message(
                    InboundMessage(
                        channel="telegram", external_user_id=dialog.user_id, text=text, business_id=DEMO_BUSINESS_ID
                    )
                )
                await session.commit()
        except Exception as exc:  # the eval reports a crash of the core instead of stopping the whole run
            dialog.error = f"agent: {type(exc).__name__}: {str(exc)[:200]}"
            dialog.end = "error"
            break
        turn.latency_ms = int((time.perf_counter() - started) * 1000)
        turn.agent = response.response_text if response.send_reply else ""
        turn.cost = response.usage.estimated_cost
        turn.model = response.model_used
        turn.route = f"{response.route}/{response.route_reason}"
        turn.handoff = next((step.partition(":")[2] for step in response.logs if step.startswith("handoff:")), None)
        turn.actions = [str(action.type) for action in response.actions]
        turn.steps = list(response.logs)
        customer_id = response.customer_id
        if status != "continue" or index == max_turns - 1:
            if status != "continue":
                dialog.end = status
            break
        try:
            line = await asyncio.wait_for(
                simulator.next(persona, [(item.customer, item.agent) for item in dialog.turns]), timeout=90
            )
        except Exception as exc:  # a simulator failure ends this dialog only
            dialog.error = f"simulator: {type(exc).__name__}: {str(exc)[:200]}"
            dialog.end = "error"
            break
        dialog.simulator_cost += line.cost
        if not line.text:
            dialog.end = line.status
            break
        text, status = line.text, line.status
    if customer_id is not None:
        async with runtime.session_factory() as session:
            customer = await CustomerRepository(session).get(customer_id)
        dialog.phone_saved = bool(customer and (customer.contact_phone or customer.phone))
    return dialog
