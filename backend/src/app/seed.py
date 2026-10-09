"""Idempotent demo data. Catalog is richer than the two-listing MVP so routing and retrieval can be stressed."""

import asyncio
from uuid import UUID

from app.config import get_settings
from app.container import build_runtime
from app.domain.enums import CustomerStatus
from app.domain.models import Business, Customer, KnowledgeItem, utcnow
from app.infrastructure.database.models import BusinessRow
from app.infrastructure.database.repositories import BusinessRepository, CustomerRepository, KnowledgeRepository
from app.migrate import upgrade_database

DEMO_BUSINESS_ID = UUID("11111111-1111-4111-8111-111111111111")
APT_CHUI = UUID("22222222-2222-4222-8222-222222222221")
APT_KIEV = UUID("22222222-2222-4222-8222-222222222222")
APT_STUDIO = UUID("22222222-2222-4222-8222-222222222223")
APT_FIL = UUID("22222222-2222-4222-8222-222222222224")
APT_JAL = UUID("22222222-2222-4222-8222-222222222225")
APT_SOLD = UUID("22222222-2222-4222-8222-222222222226")
APT_RENT = UUID("22222222-2222-4222-8222-222222222227")
FAQ_PARKING = UUID("22222222-2222-4222-8222-222222222228")
FAQ_FEE = UUID("22222222-2222-4222-8222-222222222229")
FAQ_VIEW = UUID("22222222-2222-4222-8222-22222222222a")
CUSTOMER_AIGUL = UUID("33333333-3333-4333-8333-333333333331")
CUSTOMER_NURLAN = UUID("33333333-3333-4333-8333-333333333332")
CUSTOMER_BERMET = UUID("33333333-3333-4333-8333-333333333333")

_BUSINESS_DESCRIPTION = (
    "Агентство недвижимости Demo Realty в Бишкеке. Продажа и аренда квартир: "
    "центр, Филармония, Джал, Ахунбаева. Показ объекта — по записи."
)
_CONTACTS = {
    "phone": "+996555000000",
    "address": "Бишкек, проспект Чуй, 114",
    "instagram": "@demo.realty",
    "email": "hello@demorealty.kg",
    # Persona name the agent introduces itself with. One per business.
    "assistant_name": "Айпери",
}
_HOURS = "пн-сб 09:00-18:00, вс выходной"
_RULES = (
    "Не выдумывать цены, наличие, сроки и условия оплаты. "
    "Если факта нет в базе знаний — передать менеджеру. "
    "Условия оплаты называет только база знаний, не общие слова агентства."
)

KNOWLEDGE = (
    (
        APT_STUDIO,
        "property",
        "Студия на Ахунбаева",
        "Студия, 1 комната, 28 м², 2 этаж, район Ахунбаева, цена 39000 USD. Статус: доступна. Без ремонта.",
    ),
    (
        APT_FIL,
        "property",
        "Однушка у Филармонии",
        "1-комнатная квартира, 41 м², 4 этаж, район Филармония, цена 62000 USD. Статус: доступна. Есть лифт.",
    ),
    (
        APT_CHUI,
        "property",
        "Квартира на Чуй",
        "2-комнатная квартира, 58 м², 5 этаж, проспект Чуй, цена 85000 USD. Статус: доступна. Для двоих подходит.",
    ),
    (
        APT_KIEV,
        "property",
        "Квартира на Киевской",
        "3-комнатная квартира, 76 м², 8 этаж, улица Киевская, цена 110000 USD. Статус: доступна. Подземная парковка.",
    ),
    (
        APT_JAL,
        "property",
        "Четырёхкомнатная на Джале",
        "4-комнатная квартира, 125 м², 9 этаж, микрорайон Джал, цена 165000 USD. Статус: доступна. Семейный вариант.",
    ),
    (
        APT_SOLD,
        "property",
        "Квартира на Советской (продана)",
        "2-комнатная квартира, 55 м², 3 этаж, улица Советская, цена 79000 USD. Статус: продана, не предлагать.",
    ),
    (
        APT_RENT,
        "property",
        "Аренда на Токтогула",
        "1-комнатная квартира в аренду, 38 м², 6 этаж, улица Токтогула. Аренда 450 USD в месяц. Статус: доступна.",
    ),
    (
        FAQ_PARKING,
        "faq",
        "Парковка",
        "Подземная парковка есть у объекта на Киевской и у четырёхкомнатной на Джале. На Ахунбаева и Чуй — только двор.",
    ),
    (
        FAQ_FEE,
        "faq",
        "Комиссия",
        "Комиссия для покупателя 0 процентов. Комиссия продавца 2 процента от цены сделки.",
    ),
    (
        FAQ_VIEW,
        "faq",
        "Показы",
        "Показ квартиры ежедневно с 10:00 до 17:00 по предварительной записи. Документы объекта показывает менеджер на месте.",
    ),
)


async def seed(session) -> Business:
    """Insert Demo Realty, the catalog and seed customers. Safe to run twice."""

    businesses = BusinessRepository(session)
    knowledge = KnowledgeRepository(session)
    customers = CustomerRepository(session)
    now = utcnow()

    business = await businesses.get_by_name("Demo Realty")
    if business is None:
        business = Business(
            id=DEMO_BUSINESS_ID,
            name="Demo Realty",
            description=_BUSINESS_DESCRIPTION,
            working_hours=_HOURS,
            contacts=dict(_CONTACTS),
            rules=_RULES,
            created_at=now,
            updated_at=now,
        )
        await businesses.add(business)
    else:
        row = await session.get(BusinessRow, business.id)
        if row is not None:
            row.description = _BUSINESS_DESCRIPTION
            row.working_hours = _HOURS
            row.contacts = dict(_CONTACTS)
            row.rules = _RULES
            row.updated_at = now
            await session.flush()
            business = await businesses.get(business.id) or business

    for item_id, category, title, content in KNOWLEDGE:
        existing = await knowledge.get_by_title(business.id, title)
        if existing is not None:
            continue
        await knowledge.add(
            KnowledgeItem(
                id=item_id,
                business_id=business.id,
                category=category,
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
        business.id,
        CUSTOMER_AIGUL,
        phone="+996555111222",
        channel="whatsapp",
        external_id="+996555111222",
        language="ru",
    )
    await _customer(
        customers,
        business.id,
        CUSTOMER_NURLAN,
        phone=None,
        channel="instagram",
        external_id="ig_nurlan",
        language="ru",
    )
    await _customer(
        customers,
        business.id,
        CUSTOMER_BERMET,
        phone=None,
        channel="telegram",
        external_id="tg_bermet",
        language="ky",
    )
    return business


async def _customer(
    customers: CustomerRepository, business_id: UUID, customer_id: UUID, phone, channel, external_id, language
) -> None:
    existing = None
    if phone:
        existing = await customers.get_by_phone(business_id, phone)
    if existing is None:
        existing = await customers.get_by_channel(business_id, channel, external_id)
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
                business_id=business_id,
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
