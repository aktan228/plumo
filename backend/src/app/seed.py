"""Idempotent demo data for Demo Realty."""

import asyncio
from uuid import UUID

from app.config import get_settings
from app.container import build_runtime
from app.domain.enums import CustomerStatus
from app.domain.models import Business, Customer, KnowledgeItem, utcnow
from app.infrastructure.database.repositories import BusinessRepository, CustomerRepository, KnowledgeRepository
from app.migrate import upgrade_database

DEMO_BUSINESS_ID = UUID("11111111-1111-4111-8111-111111111111")
APT_CHUI = UUID("22222222-2222-4222-8222-222222222221")
APT_KIEV = UUID("22222222-2222-4222-8222-222222222222")
CUSTOMER_AIGUL = UUID("33333333-3333-4333-8333-333333333331")
CUSTOMER_NURLAN = UUID("33333333-3333-4333-8333-333333333332")


async def seed(session) -> Business:
    """Insert the demo business, two listings and two customers. Safe to run twice."""

    businesses = BusinessRepository(session)
    knowledge = KnowledgeRepository(session)
    customers = CustomerRepository(session)
    now = utcnow()

    business = await businesses.get_by_name("Demo Realty")
    if business is None:
        business = Business(
            id=DEMO_BUSINESS_ID,
            name="Demo Realty",
            description="Агентство недвижимости в Бишкеке",
            working_hours="09:00-18:00",
            contacts={"phone": "+996555000000", "address": "Бишкек, проспект Чуй"},
            rules="Не выдумывать цены, наличие, сроки и условия. Если факта нет в базе — передать менеджеру.",
            created_at=now,
            updated_at=now,
        )
        await businesses.add(business)

    listings = [
        (
            APT_CHUI,
            "Квартира на Чуй",
            "2-комнатная квартира, 58 м², 5 этаж, цена 85000 USD. Статус: доступна.",
        ),
        (
            APT_KIEV,
            "Квартира на Киевской",
            "3-комнатная квартира, 76 м², 8 этаж, цена 110000 USD. Статус: доступна.",
        ),
    ]
    for item_id, title, content in listings:
        if await knowledge.get_by_title(business.id, title):
            continue
        await knowledge.add(
            KnowledgeItem(
                id=item_id,
                business_id=business.id,
                category="property",
                title=title,
                content=content,
                metadata={},
                active=True,
                created_at=now,
                updated_at=now,
            )
        )

    await _customer(
        customers,
        CUSTOMER_AIGUL,
        phone="+996555111222",
        channel="whatsapp",
        external_id="+996555111222",
        language="ru",
    )
    await _customer(
        customers,
        CUSTOMER_NURLAN,
        phone=None,
        channel="instagram",
        external_id="ig_nurlan",
        language="ru",
    )
    return business


async def _customer(customers: CustomerRepository, customer_id: UUID, phone, channel, external_id, language) -> None:
    existing = None
    if phone:
        existing = await customers.get_by_phone(phone)
    if existing is None:
        existing = await customers.get_by_channel(channel, external_id)
    now = utcnow()
    if existing is None:
        await customers.add(
            Customer(
                id=customer_id,
                phone=phone,
                language=language,
                status=CustomerStatus.new,
                need=None,
                preferred_contact_channel=channel,
                merged_into_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        await customers.link_channel(customer_id, channel, external_id)
        return
    await customers.link_channel(existing.id, channel, external_id)


async def main() -> None:
    settings = get_settings()
    runtime = build_runtime(settings)
    async with runtime.session_factory() as session:
        business = await seed(session)
        await session.commit()
    print(f"seeded business {business.id} ({business.name})")
    await runtime.engine.dispose()


if __name__ == "__main__":
    upgrade_database()
    asyncio.run(main())
