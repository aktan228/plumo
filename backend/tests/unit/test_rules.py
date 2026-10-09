"""Router, validator, language and phone rules. No database."""

from datetime import UTC, datetime
from uuid import uuid4

from app.application.services.grounded_reply import is_unusable_reply, quote_knowledge
from app.application.services.knowledge_retriever import SimpleKnowledgeRetriever
from app.application.services.response_validator import ResponseValidator
from app.application.services.router import RuleBasedRouter
from app.domain.models import AgentContext, Business, Customer, KnowledgeHit, KnowledgeItem
from app.domain.phrases import (
    HUMAN_CHAT_RU,
    ROLE_PHRASE_RU,
    UNKNOWN_FACT_KY,
    UNKNOWN_FACT_RU,
    UNKNOWN_INSTALLMENT_RU,
)
from app.domain.text_signals import analyze_message, detect_language, find_phones, normalize_phone
from app.infrastructure.ai.mock_llm import MockLanguageDetector


def _business() -> Business:
    now = datetime.now(UTC)
    return Business(
        id=uuid4(),
        name="Demo Realty",
        description="Агентство",
        working_hours="09:00-18:00",
        contacts={"phone": "+996555000000", "address": "Бишкек, проспект Чуй"},
        rules="Не выдумывать.",
        created_at=now,
        updated_at=now,
    )


def _customer() -> Customer:
    now = datetime.now(UTC)
    return Customer(
        id=uuid4(),
        phone="+996555000111",
        language="ru",
        status="active",
        need=None,
        preferred_contact_channel="whatsapp",
        merged_into_id=None,
        created_at=now,
        updated_at=now,
    )


def _item(content: str, title: str = "Квартира на Чуй") -> KnowledgeItem:
    now = datetime.now(UTC)
    return KnowledgeItem(
        id=uuid4(),
        business_id=uuid4(),
        category="property",
        title=title,
        content=content,
        metadata={},
        active=True,
        created_at=now,
        updated_at=now,
    )


def _context(text: str, items: list[KnowledgeItem] | None = None) -> AgentContext:
    hits = [KnowledgeHit(item=item, score=float(index + 1)) for index, item in enumerate(items or [])]
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return AgentContext(
        agent_instructions="test",
        business=_business(),
        knowledge=hits,
        customer=_customer(),
        summary=None,
        recent_messages=[],
        current_message=text,
        language="ru",
    )


async def test_greeting_only_routes_small():
    decision = await RuleBasedRouter().select_model(_context("Здравствуйте"))
    assert decision.model == "small"
    assert decision.reason == "greeting"


async def test_products_with_hello_are_not_a_pure_greeting():
    item = _item("2-комнатная квартира, 58 м², 5 этаж, цена 85000 USD. Статус: доступна.")
    other = _item("1-комнатная квартира, 41 м², цена 62000 USD. Статус: доступна.", "Однушка")
    context = _context("привет, подскажи какие товары у вас есть", [item, other])
    decision = await RuleBasedRouter().select_model(context)
    assert decision.reason != "greeting"


async def test_simple_question_routes_small():
    item = _item("2-комнатная квартира, 58 м², 5 этаж, цена 85000 USD. Статус: доступна.")
    other = _item("3-комнатная квартира, 76 м², 8 этаж, цена 110000 USD. Статус: доступна.", "Квартира на Киевской")
    context = _context("Еще продается квартира за 85000?", [other, item])
    context.knowledge = [KnowledgeHit(item, 6), KnowledgeHit(other, 1)]
    decision = await RuleBasedRouter().select_model(context)
    assert decision.model == "small"
    assert decision.reason == "knowledge_base_simple_question"


async def test_installment_routes_big():
    decision = await RuleBasedRouter().select_model(_context("А рассрочка есть?"))
    assert decision.model == "big"
    assert decision.reason == "money_or_installment"


async def test_mixed_language_routes_big():
    decision = await RuleBasedRouter().select_model(_context("Салам, квартира еще продается?"))
    assert decision.model == "big"
    assert decision.reason == "mixed_language"


async def test_validator_blocks_unknown_price():
    context = _context(
        "сколько стоит?",
        [_item("2-комнатная квартира, 58 м², 5 этаж, цена 85000 USD. Статус: доступна.")],
    )
    result = ResponseValidator().validate("Есть вариант за 99000 USD.", context)
    assert result.safe is False
    assert result.reason == "invented_number"


async def test_validator_allows_known_price():
    context = _context(
        "сколько стоит?",
        [_item("2-комнатная квартира, 58 м², 5 этаж, цена 85000 USD. Статус: доступна.")],
    )
    result = ResponseValidator().validate("Да, объект за 85 000 USD ещё доступен. 2-комнатная квартира, 58 м², 5 этаж.", context)
    assert result.safe is True


async def test_every_fallback_variant_passes_the_validator():
    context = _context("А рассрочка есть?")
    lines = [*UNKNOWN_INSTALLMENT_RU, *UNKNOWN_FACT_RU, *UNKNOWN_FACT_KY, *ROLE_PHRASE_RU, *HUMAN_CHAT_RU]
    for line in lines:
        assert ResponseValidator().validate(line, context).safe is True, line


async def test_quote_knowledge_hides_internal_notes_and_sounds_human():
    sold = _item("2-комнатная, 55 м², цена 79000 USD. Статус: продана, не предлагать.", title="Советская")
    live = _item("2-комнатная квартира, 58 м², цена 85000 USD. Статус: доступна.")
    text = quote_knowledge(_context("какие есть квартиры?", [sold, live]))
    assert "Советская" not in text
    assert "Статус" not in text
    assert "В базе" not in text
    assert "85000" in text
    assert ResponseValidator().validate(text, _context("какие есть квартиры?", [sold, live])).safe


async def test_language_detection():
    assert detect_language("Здравствуйте, квартира еще продается?") == "ru"
    assert detect_language("Салам, кантип баасы?") == "ky"
    assert detect_language("Салам, квартира еще продается?") == "mixed"
    assert detect_language("hello") == "unknown"
    detector = MockLanguageDetector()
    assert await detector.detect("Салам") == "ky"


def test_phone_normalization():
    assert normalize_phone("+996 555 123 456") == "+996555123456"
    assert normalize_phone("0555123456") == "+996555123456"
    assert normalize_phone("85000") is None
    assert find_phones("мой номер +996555111222") == ["+996555111222"]


def test_meeting_clock_is_not_an_invented_price():
    text = "Могу предложить встречу 2026-10-05 15:00. Если время неудобно, напишите другое."
    extra = '{"datetime": "2026-10-05T15:00:00+00:00", "time": "15:00"}'
    result = ResponseValidator().validate(text, _context("Хочу встречу завтра в 15:00"), extra)
    assert result.safe is True


def test_installment_signal():
    signals = analyze_message("А рассрочка есть?")
    assert signals.installment is True
    assert signals.complex is True


def test_catalog_query_scores_listings():
    item = _item("2-комнатная квартира, 58 м², 5 этаж, цена 85000 USD. Статус: доступна.")
    assert SimpleKnowledgeRetriever.score("привет, что продается?", item) >= 2
    assert SimpleKnowledgeRetriever.score("посмотри именно со своей базы данных", item) >= 2


def test_short_russian_ack_is_usable():
    assert is_unusable_reply("Хорошо.") is False
    assert is_unusable_reply("ok") is True
    assert is_unusable_reply("User Safety: safe") is True


def test_two_people_is_not_a_human_request():
    assert analyze_message("мне нужна более дешевая квартира для двух человек").human_request is False
    assert analyze_message("позовите менеджера").human_request is True


def test_products_greeting_is_a_catalog_question():
    signals = analyze_message("привет, подскажи какие товары у вас есть")
    assert signals.greeting is True
    assert signals.catalog is True
    assert signals.factual is True
    assert signals.human_request is False


def test_budget_for_three_is_a_recommend():
    signals = analyze_message("а что ты посоветуешь для 3 человек с ограниченым бюджетом")
    assert signals.recommend is True
    assert signals.money is True
    assert signals.human_request is False


# --- regressions found by the live eval (app.eval_live) --------------------


class _Store:
    def __init__(self, items):
        self.items = items

    async def list_active(self, business_id):
        return self.items


async def test_cheaper_returns_catalog_by_price_without_sold_or_rent():
    items = [
        _item("2-комнатная квартира, цена 85000 USD. Статус: доступна.", title="Квартира на Чуй"),
        _item("Студия, цена 39000 USD. Статус: доступна.", title="Студия на Ахунбаева"),
        _item("2-комнатная, цена 79000 USD. Статус: продана, не предлагать.", title="Советская"),
        _item("Аренда 450 USD в месяц.", title="Аренда на Токтогула"),
    ]
    hits = await SimpleKnowledgeRetriever(_Store(items)).retrieve(uuid4(), "а можно дешевле что-нибудь?")
    assert [hit.item.title for hit in hits] == ["Студия на Ахунбаева", "Квартира на Чуй"]


async def test_kyrgyz_suffix_still_finds_the_listing():
    items = [
        _item("Студия, район Ахунбаева, цена 39000 USD.", title="Студия на Ахунбаева"),
        _item("4-комнатная, микрорайон Джал, цена 165000 USD.", title="Четырёхкомнатная на Джале"),
    ]
    hits = await SimpleKnowledgeRetriever(_Store(items)).retrieve(uuid4(), "Салам, Джалдагы квартиранын баасы канча?")
    assert hits[0].item.title == "Четырёхкомнатная на Джале"


def test_weekday_meeting_lands_on_that_weekday():
    from app.domain.scheduling import BUSINESS_TZ, parse_slot

    now = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)  # Thursday in Bishkek
    slot = parse_slot("давайте посмотрим в субботу в 11:00", {}, now)
    assert (slot.weekday(), slot.day, slot.hour) == (5, 10, 11)
    assert slot.tzinfo == BUSINESS_TZ


def test_lets_view_is_a_meeting():
    assert analyze_message("давайте посмотрим однушку у Филармонии").meeting
    assert analyze_message("запишите меня на субботу").meeting


def test_cut_off_json_never_reaches_the_customer():
    from app.infrastructure.ai.openrouter_llm import parse_generation_json

    parsed = parse_generation_json('{\n  "text": "Жакшы, ойлонуп көрүңүз. Сизге')
    assert parsed["text"] == "Жакшы, ойлонуп көрүңүз."
    assert parse_generation_json('{"text": "Сизге')["text"] == ""


def test_has_slot_needs_a_day_or_time():
    from app.domain.scheduling import has_slot

    assert not has_slot("да давайте, запишите нас на показ")
    assert has_slot("запишите на субботу")
    assert has_slot("давайте завтра")
    assert has_slot("в 11:00 удобно")


def test_reply_cut_before_the_list_is_unusable():
    assert is_unusable_reply("Понимаю. У нас есть два более доступных варианта:")
    assert not is_unusable_reply("Есть студия за 39000 USD. Посмотрим?")


async def test_greeting_with_a_question_is_routed_by_the_question() -> None:
    route = await RuleBasedRouter().select_model(_context("Здравствуйте, где вы находитесь?"))
    assert route.reason == "address"


async def test_renting_finds_the_rental_not_the_sales() -> None:
    from app.bench.run import build_context
    from app.bench.scenarios import SCENARIOS

    scenario = next(item for item in SCENARIOS if item.id == "base_rent")
    context = await build_context(scenario)
    assert context.knowledge[0].item.title == "Аренда на Токтогула"


async def test_validator_blocks_false_booking_and_false_transfer():
    context = _context("давайте в субботу в 11:00")
    validator = ResponseValidator()
    for line in ("Отлично, записала вас на просмотр.", "Вы записаны на субботу.", "Перевожу вас на менеджера, оставайтесь на линии."):
        assert validator.validate(line, context).safe is False, line
    assert validator.validate("Передам менеджеру выбранное время, он подтвердит.", context).safe is True


async def test_meeting_lines_never_claim_a_booking():
    from app.domain.phrases import MEETING_ASK_KY, MEETING_ASK_RU, MEETING_SET_KY, MEETING_SET_RU

    context = _context("давайте в субботу")
    for line in (*MEETING_ASK_RU, *MEETING_ASK_KY, *MEETING_SET_RU, *MEETING_SET_KY):
        assert ResponseValidator().validate(line, context).safe is True, line
