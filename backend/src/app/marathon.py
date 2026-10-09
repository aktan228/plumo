"""Strict conversation, identity and load marathon. Uses mock LLM unless AI_MODE=production.

    python -m app.marathon
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.container import build_agent, build_runtime
from app.domain.models import InboundMessage
from app.infrastructure.database.models import CustomerChannelRow, CustomerRow, MessageRow
from app.infrastructure.database.repositories import (
    BusinessRepository,
    ConversationRepository,
    CustomerRepository,
    MessageRepository,
    SummaryRepository,
)
from app.migrate import upgrade_database
from app.seed import seed


@dataclass
class Expect:
    handoff: bool | None = None
    reason: str | None = None
    route: str | None = None
    contains: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    language: str | None = None
    meeting: bool | None = None


@dataclass
class Turn:
    text: str
    channel: str = "whatsapp"
    external: str = "+996700000001"
    expect: Expect = field(default_factory=Expect)
    name: str = ""


class CaseFailed(AssertionError):
    pass


def _msg(turn: Turn) -> InboundMessage:
    return InboundMessage(channel=turn.channel, external_user_id=turn.external, text=turn.text)


def _check(name: str, turn: Turn, response) -> None:
    exp = turn.expect
    text = response.response_text
    if exp.handoff is not None and response.handoff_required is not exp.handoff:
        raise CaseFailed(f"{name}: handoff={response.handoff_required} want {exp.handoff}; text={text!r}")
    if exp.reason and response.handoff_reason != exp.reason:
        raise CaseFailed(f"{name}: reason={response.handoff_reason!r} want {exp.reason!r}")
    if exp.route and response.route != exp.route:
        raise CaseFailed(f"{name}: route={response.route} want {exp.route}")
    if exp.language and response.language != exp.language:
        raise CaseFailed(f"{name}: language={response.language} want {exp.language}")
    if exp.meeting is True and not any(item.type == "schedule_meeting" for item in response.actions):
        raise CaseFailed(f"{name}: expected schedule_meeting, actions={response.actions}")
    for needle in exp.contains:
        if needle.lower() not in text.lower():
            raise CaseFailed(f"{name}: missing {needle!r} in {text!r}")
    for needle in exp.forbidden:
        if needle.lower() in text.lower():
            raise CaseFailed(f"{name}: forbidden {needle!r} leaked into {text!r}")


DIALOGUES: list[tuple[str, list[Turn]]] = [
    (
        "greeting_ru",
        [Turn("Здравствуйте", external="+996700100001", expect=Expect(handoff=False, contains=("Здравствуйте",)))],
    ),
    (
        "greeting_ky",
        [
            Turn(
                "Салам",
                channel="telegram",
                external="tg-ky-1",
                expect=Expect(handoff=False, language="ky", contains=("Салам",)),
            )
        ],
    ),
    (
        "farewell",
        [Turn("До свидания", external="+996700100002", expect=Expect(handoff=False, contains=("свидания",)))],
    ),
    (
        "yes",
        [Turn("да", external="+996700100003", expect=Expect(handoff=False, contains=("Хорошо",)))],
    ),
    (
        "hours",
        [
            Turn(
                "Какой у вас график работы?",
                external="+996700100004",
                expect=Expect(handoff=False, contains=("09:00", "18:00")),
            )
        ],
    ),
    (
        "address",
        [
            Turn(
                "Где вы находитесь, какой адрес?",
                external="+996700100005",
                expect=Expect(handoff=False, contains=("Чуй",)),
            )
        ],
    ),
    (
        "contacts",
        [
            Turn(
                "Как связаться, ваш телефон?",
                external="+996700100006",
                expect=Expect(handoff=False, contains=("996555000000",)),
            )
        ],
    ),
    (
        "catalog",
        [
            Turn(
                "какие есть квартиры в продаже?",
                external="+996700100007",
                expect=Expect(handoff=False, contains=("USD",), forbidden=("рассрочк", "999999")),
            )
        ],
    ),
    (
        "products_hello",
        [
            Turn(
                "привет, подскажи какие товары у вас есть",
                external="+996700100027",
                expect=Expect(handoff=False, forbidden=("устройств", "нейросет")),
            )
        ],
    ),
    (
        "chui_85000",
        [
            Turn(
                "Еще продается квартира за 85000?",
                external="+996700100008",
                expect=Expect(handoff=False, route="small", contains=("85 000", "2-комнат")),
            )
        ],
    ),
    (
        "studio_39000",
        [
            Turn(
                "есть студия за 39000?",
                external="+996700100009",
                expect=Expect(handoff=False, contains=("39 000",), forbidden=("165000", "165 000")),
            )
        ],
    ),
    (
        "filarmonia_62000",
        [
            Turn(
                "однушка у Филармонии ещё продается, 62000?",
                external="+996700100010",
                expect=Expect(handoff=False, contains=("62 000",), forbidden=("110 000",)),
            )
        ],
    ),
    (
        "jal_family",
        [
            Turn(
                "нужна большая квартира на Джале за 165000",
                external="+996700100011",
                expect=Expect(handoff=False, contains=("165 000", "4-комнат")),
            )
        ],
    ),
    (
        "missing_price",
        [
            Turn(
                "есть квартира за 50000?",
                external="+996700100012",
                expect=Expect(
                    handoff=True,
                    reason="no_knowledge",
                    forbidden=("50 000", "50000", "85 000", "90000"),
                ),
            )
        ],
    ),
    (
        "fantasy_price",
        [
            Turn(
                "квартира за 999999 есть?",
                external="+996700100013",
                expect=Expect(handoff=True, forbidden=("999999", "1 000 000")),
            )
        ],
    ),
    (
        "installment",
        [
            Turn(
                "А рассрочка есть?",
                external="+996700100014",
                expect=Expect(handoff=True, reason="no_knowledge", contains=("рассрочк",), forbidden=("есть рассрочка",)),
            )
        ],
    ),
    (
        "mortgage_word",
        [
            Turn(
                "можно в ипотеку?",
                external="+996700100015",
                expect=Expect(handoff=True, reason="no_knowledge"),
            )
        ],
    ),
    (
        "two_people_cheaper",
        [
            Turn(
                "мне нужна более дешевая квартира для двух человек",
                external="+996700100016",
                expect=Expect(handoff=False, forbidden=("подключаю менеджера", "передаю менеджеру")),
            )
        ],
    ),
    (
        "human_request",
        [
            Turn(
                "Позовите менеджера",
                external="+996700100017",
                expect=Expect(handoff=True, reason="user_requested_human"),
            )
        ],
    ),
    (
        "operator_request",
        [
            Turn(
                "соедините с оператором",
                external="+996700100018",
                expect=Expect(handoff=True, reason="user_requested_human"),
            )
        ],
    ),
    (
        "meeting",
        [
            Turn(
                "Хочу записаться на встречу завтра в 15:00",
                external="+996700100019",
                expect=Expect(meeting=True, contains=("15:00",)),
            )
        ],
    ),
    (
        "emotional",
        [
            Turn(
                "вы ужас как плохо работаете, бесите",
                external="+996700100020",
                expect=Expect(handoff=True, reason="customer_dissatisfied"),
            )
        ],
    ),
    (
        "hot_lead",
        [
            Turn(
                "беру, готов купить, оформляем задаток",
                external="+996700100021",
                expect=Expect(handoff=True, reason="hot_lead"),
            )
        ],
    ),
    (
        "mixed_language",
        [
            Turn(
                "Салам, квартира еще продается?",
                external="+996700100022",
                expect=Expect(language="mixed"),
            )
        ],
    ),
    (
        "about_ai",
        [
            Turn(
                "можешь рассказать про себя как ИИ, как тебя создали",
                external="+996700100023",
                expect=Expect(forbidden=("110000", "165000", "39000")),
            )
        ],
    ),
    (
        "objection",
        [Turn("дорого, подумаю, не сейчас", external="+996700100024", expect=Expect(handoff=False))],
    ),
    (
        "multi_turn_same_phone",
        [
            Turn("Здравствуйте", external="+996700100025", expect=Expect(handoff=False)),
            Turn("какие есть квартиры?", external="+996700100025", expect=Expect(handoff=False)),
            Turn("А рассрочка есть?", external="+996700100025", expect=Expect(handoff=True, reason="no_knowledge")),
        ],
    ),
    (
        "unclear_then_fact",
        [
            Turn("ну", external="+996700100026", channel="telegram"),
            Turn("Еще продается квартира за 85000?", external="+996700100026", channel="telegram", expect=Expect(handoff=False, contains=("85 000",))),
        ],
    ),
]


async def run_dialogues(agent) -> list[str]:
    failures: list[str] = []
    for name, turns in DIALOGUES:
        ids: set[UUID] = set()
        try:
            for index, turn in enumerate(turns):
                response = await agent.process_message(_msg(turn))
                ids.add(response.customer_id)
                _check(f"{name}[{index}]", turn, response)
            if len(ids) != 1:
                raise CaseFailed(f"{name}: customer id jumped {ids}")
        except CaseFailed as exc:
            failures.append(str(exc))
    return failures


async def run_identity(agent, session) -> list[str]:
    failures: list[str] = []
    customers = CustomerRepository(session)
    conversations = ConversationRepository(session)
    messages = MessageRepository(session)

    def fail(msg: str) -> None:
        failures.append(msg)

    wa = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id="+996700200001", text="Здравствуйте")
    )
    wa2 = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id="+996700200001", text="Еще продается квартира за 85000?")
    )
    if wa.customer_id != wa2.customer_id:
        fail("same whatsapp number produced two customer cards")

    local = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id="0555700200", text="привет")
    )
    e164 = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id="+996555700200", text="какие квартиры есть?")
    )
    if local.customer_id != e164.customer_id:
        fail(f"0555 and +996 did not merge: {local.customer_id} vs {e164.customer_id}")
    card = await customers.get(e164.customer_id)
    if card is None or card.phone != "+996555700200":
        fail(f"canonical phone not stored, got {card.phone if card else None}")

    voice = await agent.process_message(
        InboundMessage(channel="voice", external_user_id="+996700200001", text="Здравствуйте")
    )
    if voice.customer_id != wa.customer_id:
        fail("voice and whatsapp with same phone split the customer")

    other = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id="+996700200099", text="Здравствуйте")
    )
    if other.customer_id == wa.customer_id:
        fail("two different phones collapsed into one customer")

    ig = await agent.process_message(
        InboundMessage(channel="instagram", external_user_id="ig_merge_200003", text="привет")
    )
    if ig.customer_id == wa.customer_id:
        fail("instagram without phone should be a separate card")
    typed = await agent.process_message(
        InboundMessage(
            channel="instagram",
            external_user_id="ig_merge_200003",
            text="мой номер +996700200001",
        )
    )
    # A typed number is a callback contact, not proof of identity: no merge.
    if typed.customer_id != ig.customer_id:
        fail(f"typed phone merged instagram into another card: {typed.customer_id}")
    ig_row = await customers.get(ig.customer_id)
    if ig_row is None or ig_row.contact_phone != "+996700200001" or ig_row.status == "merged":
        fail(f"typed phone was not kept as contact on the instagram card: {ig_row}")

    convs = await conversations.list_for_customer(wa.customer_id)
    channels = {item.channel for item in convs}
    if not {"whatsapp", "voice"} <= channels or "instagram" in channels:
        fail(f"phone owner card has wrong channels: {channels}")
    history = await messages.list_for_customer(wa.customer_id)
    if len(history) < 4:
        fail(f"history too thin for the phone owner: {len(history)}")

    tg = await agent.process_message(
        InboundMessage(channel="telegram", external_user_id="tg_keep_phone", text="салам")
    )
    kept = await agent.process_message(
        InboundMessage(
            channel="telegram",
            external_user_id="tg_keep_phone",
            text="мой номер +996700200099",
        )
    )
    if kept.customer_id != tg.customer_id or kept.customer_id == other.customer_id:
        fail(f"telegram card must stay separate from +996700200099, got {kept.customer_id}")

    # A card that already has a phone must not steal another person's number.
    steal = await agent.process_message(
        InboundMessage(
            channel="whatsapp",
            external_user_id="+996700200001",
            text="перезвоните на +996700200099",
        )
    )
    if steal.customer_id != wa.customer_id:
        fail("existing-phone card jumped identity after seeing another number in text")
    still = await customers.get(wa.customer_id)
    if still is None or still.phone != "+996700200001":
        fail(f"survivor phone was overwritten, got {still.phone if still else None}")

    seed_aigul = await customers.get_by_phone(await _demo_business_id(session), "+996555111222")
    if seed_aigul is None:
        fail("seed customer Aigul missing by phone")
    again = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id="+996555111222", text="график работы какой?")
    )
    if seed_aigul and again.customer_id != seed_aigul.id:
        fail("seed WhatsApp phone created a duplicate instead of reusing Aigul")

    summary = await SummaryRepository(session).get(wa.customer_id)
    if summary is None or not summary.summary:
        fail("summary was not written for the phone owner")
    return failures


async def _demo_business_id(session) -> UUID:
    business = await BusinessRepository(session).get_by_name("Demo Realty")
    if business is None:
        raise RuntimeError("seed the demo business first")
    return business.id


async def run_persistence_sql(session, customer_id: UUID, phone: str) -> list[str]:
    failures: list[str] = []
    phones = await session.scalars(select(CustomerRow.phone).where(CustomerRow.id == customer_id))
    stored = list(phones)
    if stored != [phone]:
        failures.append(f"customers.phone for {customer_id} is {stored}, want [{phone}]")
    links = (
        await session.scalars(select(CustomerChannelRow.channel).where(CustomerChannelRow.customer_id == customer_id))
    ).all()
    if "whatsapp" not in links:
        failures.append(f"no whatsapp link for {customer_id}: {links}")
    count = await session.scalar(select(func.count()).select_from(MessageRow).where(MessageRow.customer_id == customer_id))
    if not count or count < 2:
        failures.append(f"messages not saved for {customer_id}: {count}")
    return failures


async def run_load(runtime, count: int = 40) -> list[str]:
    failures: list[str] = []
    started = time.perf_counter()

    async def one(index: int) -> UUID:
        phone = f"+996701{index:06d}"
        async with runtime.session_factory() as session:
            agent = build_agent(session, runtime)
            first = await agent.process_message(
                InboundMessage(channel="whatsapp", external_user_id=phone, text="Здравствуйте")
            )
            second = await agent.process_message(
                InboundMessage(
                    channel="whatsapp",
                    external_user_id=phone,
                    text="Еще продается квартира за 85000?",
                )
            )
            third = await agent.process_message(
                InboundMessage(channel="whatsapp", external_user_id=phone, text="А рассрочка есть?")
            )
            await session.commit()
            if first.customer_id != second.customer_id or second.customer_id != third.customer_id:
                raise CaseFailed(f"load {phone} split identity")
            if second.handoff_required:
                raise CaseFailed(f"load {phone} false handoff on 85000")
            if not third.handoff_required:
                raise CaseFailed(f"load {phone} missed installment handoff")
            return first.customer_id

    results = await asyncio.gather(*[one(i) for i in range(count)], return_exceptions=True)
    elapsed = time.perf_counter() - started
    ids: list[UUID] = []
    for index, item in enumerate(results):
        if isinstance(item, Exception):
            failures.append(f"load[{index}]: {item}")
        else:
            ids.append(item)
    if len(set(ids)) != len(ids):
        failures.append(f"load collapsed customers: {len(ids)} turns, {len(set(ids))} unique")
    if elapsed > 90:
        failures.append(f"load too slow: {elapsed:.1f}s for {count} users x 3 turns")
    return failures


async def run_all(*, load_users: int, live: bool = False) -> int:
    if live:
        settings = get_settings()
    else:
        os.environ["AI_MODE"] = "mock"
        get_settings.cache_clear()
        dumped = get_settings().model_dump()
        dumped.update(
            {
                "ai_mode": "mock",
                "small_model_provider": "mock",
                "big_model_provider": "mock",
            }
        )
        settings = Settings(**dumped)
    runtime = build_runtime(settings)
    failures: list[str] = []
    async with runtime.session_factory() as session:
        await seed(session)
        await session.commit()
        agent = build_agent(session, runtime)
        failures.extend(await run_dialogues(agent))
        failures.extend(await run_identity(agent, session))
        probe = await agent.process_message(
            InboundMessage(channel="whatsapp", external_user_id="+996700200001", text="ок")
        )
        failures.extend(await run_persistence_sql(session, probe.customer_id, "+996700200001"))
        await session.commit()
    failures.extend(await run_load(runtime, count=load_users))
    await runtime.engine.dispose()

    total = len(DIALOGUES) + 12 + load_users
    if failures:
        print(f"MARATHON FAIL  {len(failures)} issues  (checked ~{total} units)")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"MARATHON PASS  dialogues={len(DIALOGUES)}  identity+sql  load_users={load_users}")
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description="Plumo strict marathon")
    parser.add_argument("--load-users", type=int, default=40)
    parser.add_argument("--live", action="store_true", help="Use .env providers instead of mock")
    args = parser.parse_args()
    upgrade_database()
    raise SystemExit(asyncio.run(run_all(load_users=args.load_users, live=args.live)))


if __name__ == "__main__":
    main()
