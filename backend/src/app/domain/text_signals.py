"""Shared text signals for the rule router, the knowledge gate and the mocks.

This is not a model. It is a small, explicit lexicon so the core can route
and refuse facts without calling an LLM.
"""

import re
from dataclasses import dataclass

_YO = str.maketrans({"ё": "е", "Ё": "е"})

KY_MARKERS = frozenset(
    {
        "салам",
        "рахмат",
        "жакшы",
        "кантип",
        "эмне",
        "баасы",
        "барбы",
        "жок",
        "ооба",
        "сиз",
        "бул",
        "эмес",
        "сатылат",
        "керек",
        "болот",
        "кайда",
        "качан",
        "мен",
        "жолугу",
    }
)

RU_MARKERS = frozenset(
    {
        "здравствуйте",
        "привет",
        "пожалуйста",
        "квартира",
        "есть",
        "цена",
        "еще",
        "менеджер",
        "встреч",
        "рассроч",
        "подскажите",
        "добрый",
        "продается",
        "доступен",
        "сколько",
        "объект",
        "хочу",
        "можно",
    }
)

GREETING = ("здравствуйте", "привет", "добрый день", "добрый вечер", "салам", "hello", "hi")
FAREWELL = ("до свидания", "пока", "всего доброго", "жакшы калыныз")
CLEAR_CONFIRM = frozenset({"да", "нет", "ок", "хорошо", "ооба", "жок"})
UNCLEAR_CONFIRM = frozenset({"ну", "угу", "ага", "хм", "эм"})
HUMAN = ("менеджер", "оператор", "человек", "живой", "позовите", "соедините", "адам")
MEETING = ("встреч", "встретиться", "посмотреть квартиру", "записать", "жолугу", "покажите объект")
INSTALLMENT = ("рассроч", "ипотек", "кредит")
MONEY = ("дорого", "скидк", "торг", "дешевле", "бюджет")
COMPARISON = ("сравн", "чем отличается", "какая лучше", "или ту", "разниц")
OBJECTION = ("подумаю", "не уверен", "сомнева", "не сейчас", "дорого", "не надо")
EMOTIONAL = ("ужас", "бесите", "некомпетен", "жалоб", "недоволен", "отвратитель", "плохо работаете")
HOURS = ("график", "часы работ", "время работ", "до скольки", "когда работа")
ADDRESS = ("адрес", "где наход", "как добрать", "локаци")
CONTACTS = ("ваш телефон", "ваш номер", "как связать", "контакт")
AVAILABILITY = ("продае", "доступ", "в наличии", "еще прода", "сатылат", "барбы")
PRICE = ("цена", "стоит", "сколько", "баа")
HOT = ("беру", "покупаю", "оформляем", "готов купить", "задаток", "брониру")
PROPERTY = ("квартир", "комнат", "этаж", "объект", "метраж")

PHONE_RE = re.compile(
    r"(?:\+\d[\d\-\s()]{8,18}\d)|(?:(?<!\d)(?:996|0)\d[\d\-\s()]{7,16}\d)"
)


def normalize_text(value: str) -> str:
    return value.translate(_YO).lower().strip()


def normalize_phone(raw: str) -> str | None:
    """Return E.164-like `+digits`, or None when the input is not a phone."""

    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0") and len(digits) == 10:
        digits = "996" + digits[1:]
    if len(digits) < 10 or len(digits) > 15:
        return None
    return f"+{digits}"


def find_phones(text: str) -> list[str]:
    found: list[str] = []
    for match in PHONE_RE.findall(text):
        phone = normalize_phone(match)
        if phone and phone not in found:
            found.append(phone)
    return found


def compact_numbers(text: str) -> list[str]:
    """Digit groups of 4+ . Spaces inside a thousands group are removed (`85 000` -> `85000`)."""

    compact = normalize_text(text)
    previous = None
    while previous != compact:
        previous = compact
        compact = re.sub(r"(?<=\d)\s+(?=\d{3}(?!\d))", "", compact)
    return re.findall(r"\d{4,}", compact)


def contains_any(text: str, needles: tuple[str, ...] | frozenset[str]) -> bool:
    hay = normalize_text(text)
    return any(needle in hay for needle in needles)


@dataclass(frozen=True, slots=True)
class MessageSignals:
    language: str
    greeting: bool
    farewell: bool
    clear_confirmation: bool
    unclear_confirmation: bool
    human_request: bool
    meeting: bool
    installment: bool
    money: bool
    comparison: bool
    objection: bool
    emotional: bool
    hours: bool
    address: bool
    contacts: bool
    availability: bool
    price: bool
    hot_lead: bool
    property_details: bool
    numbers: tuple[str, ...]

    @property
    def factual(self) -> bool:
        return any(
            (
                self.installment,
                self.hours,
                self.address,
                self.contacts,
                self.availability,
                self.price,
                self.property_details,
                self.comparison,
                bool(self.numbers),
            )
        )

    @property
    def complex(self) -> bool:
        return any(
            (
                self.installment,
                self.money,
                self.comparison,
                self.objection,
                self.emotional,
                self.language == "mixed",
            )
        )


def detect_language(text: str) -> str:
    tokens = set(re.findall(r"[a-zа-я]+", normalize_text(text)))
    ky = bool(tokens & KY_MARKERS)
    ru = bool(tokens & RU_MARKERS) or bool(re.search(r"[а-я]", normalize_text(text))) and not ky
    # A Kyrgyz marker plus a clear Russian marker is mixed.
    ru_hit = bool(tokens & RU_MARKERS)
    if ky and ru_hit:
        return "mixed"
    if ky:
        return "ky"
    if ru or ru_hit:
        return "ru"
    if re.search(r"[а-яa-z]", normalize_text(text)):
        return "ru" if re.search(r"[а-я]", normalize_text(text)) else "unknown"
    return "unknown"


def analyze_message(text: str) -> MessageSignals:
    normalized = normalize_text(text)
    token = normalized.strip(" !?.")
    return MessageSignals(
        language=detect_language(text),
        greeting=contains_any(normalized, GREETING),
        farewell=contains_any(normalized, FAREWELL),
        clear_confirmation=token in CLEAR_CONFIRM,
        unclear_confirmation=token in UNCLEAR_CONFIRM,
        human_request=contains_any(normalized, HUMAN),
        meeting=contains_any(normalized, MEETING),
        installment=contains_any(normalized, INSTALLMENT),
        money=contains_any(normalized, MONEY),
        comparison=contains_any(normalized, COMPARISON),
        objection=contains_any(normalized, OBJECTION),
        emotional=contains_any(normalized, EMOTIONAL),
        hours=contains_any(normalized, HOURS),
        address=contains_any(normalized, ADDRESS),
        contacts=contains_any(normalized, CONTACTS),
        availability=contains_any(normalized, AVAILABILITY),
        price=contains_any(normalized, PRICE),
        hot_lead=contains_any(normalized, HOT),
        property_details=contains_any(normalized, PROPERTY),
        numbers=tuple(compact_numbers(text)),
    )
