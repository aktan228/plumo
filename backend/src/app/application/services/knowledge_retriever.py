"""Keyword retriever. An embedding retriever can replace this class later."""

import re
from uuid import UUID

from app.domain.models import KnowledgeHit
from app.domain.ports import KnowledgeStore
from app.domain.text_signals import compact_numbers, normalize_text


class SimpleKnowledgeRetriever:
    """Score active knowledge items for one business.

    Matching is exact and lexical: category, title, content, and numbers.
    AgentService depends on the retriever port, not on this class.
    """

    def __init__(self, knowledge: KnowledgeStore) -> None:
        self.knowledge = knowledge

    async def retrieve(self, business_id: UUID, query: str, limit: int = 5) -> list[KnowledgeHit]:
        items = await self.knowledge.list_active(business_id)
        ranked = [KnowledgeHit(item=item, score=self.score(query, item)) for item in items]
        ranked = [hit for hit in ranked if hit.score >= 1]
        ranked.sort(key=lambda hit: hit.score, reverse=True)
        return ranked[:limit]

    @staticmethod
    def score(query: str, item) -> float:
        hay = normalize_text(f"{item.title} {item.content} {item.category}")
        hay_numbers = set(compact_numbers(hay))
        score = 0.0
        for number in compact_numbers(query):
            if number in hay_numbers:
                score += 5
        for token in re.findall(r"[a-zа-я0-9]+", normalize_text(query)):
            if len(token) >= 4 and token in hay:
                score += 1
        return score
