"""Keyword retriever. An embedding retriever can replace this class later."""

import re
from uuid import UUID

from app.domain.models import KnowledgeHit
from app.domain.ports import KnowledgeStore
from app.domain.text_signals import compact_numbers, normalize_text

_TOKEN = re.compile(r"[a-zа-яңөү0-9]+")
_PRICE = re.compile(r"(\d[\d\s]*\d|\d)\s*usd")
# Renting, not buying: "снять", "аренда", Kyrgyz "ижара". Rentals go up instead of down.
_RENT = ("снять", "сниму", "снимать", "сним", "аренд", "ижара", "квартирант")
# "дешевле" means "the rest of the catalog by price", not words in a listing.
_CHEAPER = ("дешевл", "подешев", "недорог", "бюджет", "арзан")
# Three-letter words that are not names: "Чуй" and "Джал" count, "для" does not.
_STOPWORDS = frozenset(
    {"еще", "как", "что", "где", "это", "для", "вам", "нам", "мне", "все", "или", "при", "так", "там", "тут", "уже", "кто", "чем", "вас", "нас", "они", "она", "его", "бар", "жок"}
)
_CATALOG = (
    "квартир",
    "прода",
    "объект",
    "жиль",
    "апарта",
    "каталог",
    "баз",
    "наличи",
    "доступ",
    "товар",
    "ассортимент",
    "вариант",
    "совет",
    "бюджет",
)


class SimpleKnowledgeRetriever:
    """Score active knowledge items for one business.

    Matching is exact and lexical: category, title, content, and numbers.
    AgentService depends on the retriever port, not on this class.
    """

    def __init__(self, knowledge: KnowledgeStore) -> None:
        self.knowledge = knowledge

    async def retrieve(self, business_id: UUID, query: str, limit: int = 5) -> list[KnowledgeHit]:
        items = await self.knowledge.list_active(business_id)
        prepared = _PreparedQuery.from_text(query)
        if any(stem in prepared.normalized for stem in _CHEAPER):
            offers = [item for item in items if _offer(item) and _price(item) is not None]
            if offers:
                offers.sort(key=_price)
                return [KnowledgeHit(item=item, score=3.0) for item in offers[:limit]]
        ranked = [KnowledgeHit(item=item, score=_score(prepared, item)) for item in items]
        ranked.sort(key=lambda hit: hit.score, reverse=True)
        hits = [hit for hit in ranked if hit.score >= 1][:limit]
        if hits:
            return hits
        return [KnowledgeHit(item=item, score=0.5) for item in items[:limit]]

    @staticmethod
    def score(query: str, item) -> float:
        return _score(_PreparedQuery.from_text(query), item)


class _PreparedQuery:
    __slots__ = ("normalized", "numbers", "tokens", "catalog", "rent")

    def __init__(self, normalized: str, numbers: list[str], tokens: list[str], catalog: bool, rent: bool = False) -> None:
        self.normalized = normalized
        self.numbers = numbers
        self.tokens = tokens
        self.catalog = catalog
        self.rent = rent

    @classmethod
    def from_text(cls, query: str) -> "_PreparedQuery":
        normalized = normalize_text(query)
        tokens = [
            token
            for token in _TOKEN.findall(normalized)
            if len(token) >= 4 or (len(token) == 3 and token not in _STOPWORDS)
        ]
        return cls(
            normalized,
            compact_numbers(normalized),
            tokens,
            any(token in normalized for token in _CATALOG),
            any(stem in normalized for stem in _RENT),
        )


def _score(query: _PreparedQuery, item) -> float:
    hay = normalize_text(f"{item.title} {item.content} {item.category}")
    title = normalize_text(item.title)
    hay_numbers = set(compact_numbers(hay))
    score = 0.0
    for number in query.numbers:
        if number in hay_numbers:
            score += 5
    for token in query.tokens:
        if token in title:
            # Named listing ("на Чуй", "у Филармонии") outweighs shared words.
            score += 2
        elif token in hay:
            score += 1
        elif len(token) >= 6 and token[:4] in hay:
            # Kyrgyz and Russian endings: "Джалдагы" → "Джал", "Филармонияга" → "Филармония".
            score += 0.75
    if query.rent and "аренд" in hay and "продан" not in hay:
        score += 4
    if query.catalog and (item.category == "property" or "квартир" in hay):
        score += 2
        if "продан" in hay:
            score -= 2
        if "аренд" in hay and not query.rent:
            score -= 0.5
    return score


def _offer(item) -> bool:
    hay = normalize_text(f"{item.title} {item.content}")
    return item.category == "property" and "продан" not in hay and "не предлагать" not in hay and "аренд" not in hay


def _price(item) -> int | None:
    match = _PRICE.search(normalize_text(item.content))
    return int(re.sub(r"\s+", "", match.group(1))) if match else None
