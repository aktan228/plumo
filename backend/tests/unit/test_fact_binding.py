"""J-03: a price is checked against the listing it is said about, and only against current data."""

from datetime import UTC, datetime
from uuid import uuid4

from app.application.services.response_validator import ResponseValidator
from app.domain.models import AgentContext, Business, Customer, KnowledgeHit, KnowledgeItem, Message

NOW = datetime.now(UTC)


def _item(title: str, content: str) -> KnowledgeItem:
    return KnowledgeItem(uuid4(), uuid4(), "property", title, content, {}, True, NOW, NOW)


CHUI = _item("Квартира на Чуй", "2 комнаты, 58 м², 5 этаж, цена 85000 USD. Статус: доступна.")
KIEV = _item("Квартира на Киевской", "1 комната, 41 м², 3 этаж, цена 62000 USD. Статус: доступна.")


def _context(question: str, items: list[KnowledgeItem], history: list[tuple[str, str]] = ()) -> AgentContext:
    business = Business(uuid4(), "Demo Realty", "Недвижимость", "09:00-18:00", {}, "", NOW, NOW)
    customer = Customer(uuid4(), "+996555000111", "ru", "active", None, "whatsapp", None, NOW, NOW, business_id=business.id)
    messages = [Message(uuid4(), uuid4(), customer.id, role, text, NOW, {}, NOW) for role, text in history]
    return AgentContext(
        agent_instructions="test",
        business=business,
        knowledge=[KnowledgeHit(item, 1.0) for item in items],
        customer=customer,
        summary=None,
        recent_messages=messages,
        current_message=question,
        language="ru",
    )


def _check(reply: str, context: AgentContext):
    return ResponseValidator().validate(reply, context)


def test_price_of_one_listing_is_not_given_to_another():
    context = _context("Сколько стоит квартира на Чуй?", [CHUI, KIEV])
    for reply in (
        "Квартира на Чуй стоит 62 000 USD.",
        "На Чуй — 62 тысячи долларов.",
        "Квартира на Чуй — хороший вариант, стоит 62 000 USD.",
    ):
        result = _check(reply, context)
        assert (result.safe, result.reason) == (False, "misattributed_fact"), reply


def test_each_price_next_to_its_own_listing_passes():
    context = _context("Какие есть квартиры?", [CHUI, KIEV])
    for reply in (
        "Квартира на Чуй стоит 85 000 USD.",
        "Квартира на Чуй — 85 000 USD, на Киевской — 62 000 USD.",
        "На Киевской 1 комната за 62 000 USD; на Чуй 2 комнаты за 85 000 USD.",
        "Есть варианты за 85 000 и 62 000 USD.",
    ):
        assert _check(reply, context).safe, reply


def test_old_assistant_message_does_not_confirm_a_changed_price():
    updated = _item("Квартира на Чуй", "2 комнаты, 58 м², 5 этаж, цена 80000 USD. Статус: доступна.")
    context = _context(
        "А цена та же?",
        [updated],
        history=[("user", "Сколько стоит на Чуй?"), ("assistant", "Квартира на Чуй стоит 85 000 USD.")],
    )
    assert _check("Да, квартира на Чуй стоит 85 000 USD.", context).safe is False
    assert _check("Сейчас квартира на Чуй стоит 80 000 USD.", context).safe


def test_withdrawn_listing_price_is_not_confirmed_by_history():
    # The listing was switched off: it is no longer retrieved, only the old reply remembers it.
    context = _context(
        "Ещё продаётся за 85 000?",
        [],
        history=[("assistant", "Квартира на Чуй стоит 85 000 USD.")],
    )
    assert _check("Да, по-прежнему 85 000 USD.", context).safe is False


def test_customer_numbers_are_not_business_facts_but_may_be_repeated():
    context = _context("У меня бюджет до 70 000 USD, позвоните +996 555 123 456", [CHUI, KIEV])
    assert _check("Понял, бюджет до 70 000 USD. Под него подходит квартира на Киевской за 62 000 USD.", context).safe
    assert _check("Записал ваш номер +996 555 123 456, менеджер свяжется.", context).safe
    assert _check("Квартира на Чуй стоит 70 000 USD.", context).safe is False


def test_a_price_for_an_unnamed_listing_is_ambiguous():
    context = _context("Сколько стоит квартира?", [CHUI, KIEV])
    result = _check("Она стоит 85 000 USD.", context)
    assert (result.safe, result.reason) == (False, "ambiguous_object")
    # Naming the listing, or listing both, answers the question without guessing.
    assert _check("Квартира на Чуй стоит 85 000 USD, на Киевской — 62 000 USD.", context).safe
    # The customer already said which one: by name, by price or in the previous turn.
    assert _check("Она стоит 85 000 USD.", _context("Сколько стоит квартира на Чуй?", [CHUI, KIEV])).safe
    assert _check("Да, она доступна за 85 000 USD.", _context("Квартира за 85000 ещё продаётся?", [CHUI, KIEV])).safe
    followup = _context("А сколько она стоит?", [CHUI, KIEV], history=[("assistant", "Квартира на Чуй — 2 комнаты, 58 м².")])
    assert _check("Она стоит 85 000 USD.", followup).safe
    # One listing in context: nothing to confuse.
    assert _check("Она стоит 85 000 USD.", _context("Сколько стоит квартира?", [CHUI])).safe


def test_the_agent_does_not_claim_the_manager_already_got_the_notification():
    context = _context("Позовите менеджера", [CHUI])
    for reply in (
        "Менеджер уже получил ваше сообщение.",
        "Я уведомил менеджера, он в курсе.",
        "Менеджер уведомлён и скоро ответит.",
    ):
        result = _check(reply, context)
        assert (result.safe, result.reason) == (False, "unconfirmed_notification"), reply
    for reply in ("Передал ваш вопрос менеджеру, он свяжется с вами.", "Конечно, передаю менеджеру — он перезвонит вам."):
        assert _check(reply, context).safe, reply


def test_angry_kyrgyz_customer_reads_as_dissatisfied():
    """Acceptance run 2026-10-29: an angry Kyrgyz message got no handoff (angry_ky)."""

    from app.domain.text_signals import analyze_message

    assert analyze_message("Эмне мынча кечиктиңер? Жиндисиңерби, эч ким жооп бербейт!").emotional
    assert analyze_message("Мен абдан нааразымын").emotional
    assert not analyze_message("Чүйдөгү батир канча турат?").emotional
    # angry_waiting, same run: the Russian complaint passed only when the model set the flag itself.
    assert analyze_message("Третий раз пишу, никто не отвечает!").emotional
