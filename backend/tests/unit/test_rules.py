"""Router, validator, language and phone rules. No database."""

from datetime import UTC, datetime
from uuid import uuid4

from app.application.services.grounded_reply import is_unusable_reply, quote_knowledge
from app.application.services.knowledge_retriever import SimpleKnowledgeRetriever
from app.application.services.response_validator import ResponseValidator
from app.application.services.router import RuleBasedRouter
from app.domain.models import AgentContext, Business, Customer, KnowledgeHit, KnowledgeItem
from app.domain.phrases import UNKNOWN_INSTALLMENT_RU
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


async def test_simple_question_routes_small():
    item = _item("2-комнатная квартира, 58 м², 5 этаж, цена 85000 USD. Статус: доступна.")
    other = _item("3-комнатная квартира, 76 м², 8 этаж, цена 110000 USD. Статус: доступна.", "Квартира на Киевской")
    # Scores in the helper are insertion order, so give the matching item the higher score the retriever would.
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


async def test_unknown_installment_phrase_is_not_a_claim():
    context = _context("А рассрочка есть?")
    result = ResponseValidator().validate(UNKNOWN_INSTALLMENT_RU, context)
    assert result.safe is True


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
