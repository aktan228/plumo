"""Retriever cases found by the dialog eval. No database: the seed catalog stands in for the store."""

from app.application.services.knowledge_retriever import SimpleKnowledgeRetriever
from app.bench.run import _Catalog, demo_business


async def _titles(query: str) -> list[str]:
    business, items = demo_business()
    hits = await SimpleKnowledgeRetriever(_Catalog(items)).retrieve(business.id, query)
    return [hit.item.title for hit in hits]


async def test_budget_does_not_push_out_the_faq_the_question_names():
    titles = await _titles("Для себя, однушку или двушку. Бюджет до 90к. А комиссия у вас какая и чем вы лучше?")
    assert "Комиссия" in titles
    # The cheapest offers are still there for the budget part of the question.
    assert "Студия на Ахунбаева" in titles
    assert len(titles) <= 5


async def test_budget_alone_still_lists_the_cheapest_offers():
    titles = await _titles("Бюджет до 70 тысяч, что есть?")
    assert titles[0] == "Студия на Ахунбаева"
    assert "Комиссия" not in titles and "Парковка" not in titles
