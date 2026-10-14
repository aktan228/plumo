"""Demo flower catalog: shape checks, no database."""

import re

from app.application.services.knowledge_retriever import OFFER_CATEGORIES
from app.seed_flowers import CATALOG, FAQ, FLOWERS_BUSINESS_ID, _id


def test_catalog_is_rich_and_titles_are_unique() -> None:
    titles = [title for _, title, _ in (*CATALOG, *FAQ)]
    assert len(CATALOG) >= 40 and len(FAQ) >= 10
    # Rows are matched by title on reseed: a duplicate would be skipped silently.
    assert len(titles) == len(set(titles))


def test_products_are_offers_with_prices_in_som() -> None:
    for category, title, content in CATALOG:
        assert category in OFFER_CATEGORIES or category == "траур", title
        # A project price is the manager's call: the row must say so instead of a number.
        assert re.search(r"\d+\s*сом", content) or "через менеджера" in content, title


def test_ids_do_not_clash_with_the_business() -> None:
    ids = {_id(n) for n in range(1, len(CATALOG) + len(FAQ) + 1)}
    assert len(ids) == len(CATALOG) + len(FAQ)
    assert FLOWERS_BUSINESS_ID not in ids


def _store():
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(category=category, title=title, content=content)
        for category, title, content in (*CATALOG, *FAQ)
    ]

    class _Knowledge:
        async def list_active(self, business_id):
            return rows

    return _Knowledge()


async def test_budget_picks_fitting_bouquets_not_the_cheapest_extras() -> None:
    from app.application.services.knowledge_retriever import SimpleKnowledgeRetriever

    hits = await SimpleKnowledgeRetriever(_store()).retrieve(FLOWERS_BUSINESS_ID, "Хочу маме на день рождения, бюджет где-то 4 тысячи")
    titles = [hit.item.title for hit in hits]
    assert "Открытка к букету" not in titles and "Бутоньерка жениха" not in titles
    assert any("маме" in hit.item.content for hit in hits[:3])
    prices = [int(re.search(r"Цена (\d+)", hit.item.content).group(1)) for hit in hits if "Цена" in hit.item.content]
    assert prices and max(prices) <= 4000


def test_budget_amounts() -> None:
    from app.application.services.knowledge_retriever import _budget

    assert _budget("бюджет где-то 4 тысячи") == 4000
    assert _budget("до 3,5 тыс") == 3500
    assert _budget("бюджет 50 000") == 50000
    assert _budget("5000 сом") == 5000
    assert _budget("букет из 11 роз") is None


async def test_birthday_budget_never_offers_mourning_items() -> None:
    from app.application.services.knowledge_retriever import SimpleKnowledgeRetriever

    retriever = SimpleKnowledgeRetriever(_store())
    hits = await retriever.retrieve(FLOWERS_BUSINESS_ID, "От 5 до 7000 сомов, бабушке на день рождения")
    assert all(hit.item.category != "траур" for hit in hits)
    wreath = await retriever.retrieve(FLOWERS_BUSINESS_ID, "нужен траурный венок")
    assert wreath[0].item.title == "Траурный венок"
