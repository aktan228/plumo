"""Keyword retriever. An embedding retriever can replace this class later."""

import re
from uuid import UUID

from app.domain.models import KnowledgeHit
from app.domain.ports import KnowledgeStore
from app.domain.text_signals import compact_numbers, normalize_text

_TOKEN = re.compile(r"[a-zа-я0-9]+")
_CATALOG = ("квартир", "прода", "объект", "жиль", "апарта", "каталог", "баз", "наличи", "доступ")


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
    __slots__ = ("normalized", "numbers", "tokens", "catalog")

    def __init__(self, normalized: str, numbers: list[str], tokens: list[str], catalog: bool) -> None:
        self.normalized = normalized
        self.numbers = numbers
        self.tokens = tokens
        self.catalog = catalog

    @classmethod
    def from_text(cls, query: str) -> "_PreparedQuery":
        normalized = normalize_text(query)
        tokens = [token for token in _TOKEN.findall(normalized) if len(token) >= 4]
        return cls(
            normalized,
            compact_numbers(normalized),
            tokens,
            any(token in normalized for token in _CATALOG),
        )


def _score(query: _PreparedQuery, item) -> float:
    hay = normalize_text(f"{item.title} {item.content} {item.category}")
    hay_numbers = set(compact_numbers(hay))
    score = 0.0
    for number in query.numbers:
        if number in hay_numbers:
            score += 5
    for token in query.tokens:
        if token in hay:
            score += 1
    if query.catalog and (item.category == "property" or "квартир" in hay):
        score += 2
        if "продан" in hay:
            score -= 2
        if "аренд" in hay:
            score -= 0.5
    return score
