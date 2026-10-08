"""Bind a channel identity to one customer card. This service does not call a model."""

from uuid import UUID, uuid4

from app.domain.enums import PHONE_CHANNELS, CustomerStatus
from app.domain.errors import CustomerNotFound, InvalidMessage
from app.domain.events import CUSTOMER_CREATED, CUSTOMER_MERGED, DomainEvent
from app.domain.models import Customer, InboundMessage, utcnow
from app.domain.ports import CustomerStore, EventBus
from app.domain.text_signals import find_phones, phone_from_id


class CustomerResolver:
    """Resolve, link and merge customers.

    WhatsApp and voice use the phone as the primary key.
    Telegram and Instagram stay separate until the person shares a phone
    that already belongs to a card. After a merge every conversation points
    at the surviving customer.
    """

    def __init__(self, customers: CustomerStore, events: EventBus) -> None:
        self.customers = customers
        self.events = events

    async def resolve_customer(self, message: InboundMessage) -> Customer:
        if not message.external_user_id or not message.external_user_id.strip():
            raise InvalidMessage("external_user_id is required")
        external_id = message.external_user_id.strip()
        if len(external_id) > 128:
            raise InvalidMessage("external_user_id is too long")

        if message.customer_id:
            customer = await self._follow(message.customer_id)
            return await self._link_or_merge(customer, message.channel, external_id)

        phone = phone_from_id(external_id) if message.channel in PHONE_CHANNELS else None
        if phone:
            by_phone = await self.customers.get_by_phone(phone)
            if by_phone is not None:
                customer = await self._link_or_merge(by_phone, message.channel, external_id)
                if customer.preferred_contact_channel is None:
                    customer.preferred_contact_channel = message.channel
                    customer.updated_at = utcnow()
                    customer = await self.customers.save(customer)
                return customer

        by_channel = await self.customers.get_by_channel(message.channel, external_id)
        if by_channel is not None:
            customer = await self._follow(by_channel.id)
            if phone and customer.phone is None:
                customer.phone = phone
                customer.updated_at = utcnow()
                customer = await self.customers.save(customer)
            return customer

        now = utcnow()
        customer = Customer(
            id=uuid4(),
            phone=phone,
            language="unknown",
            status=CustomerStatus.new,
            need=None,
            preferred_contact_channel=message.channel,
            merged_into_id=None,
            created_at=now,
            updated_at=now,
        )
        await self.customers.add(customer)
        await self.customers.link_channel(customer.id, message.channel, external_id)
        await self.events.publish(
            DomainEvent(CUSTOMER_CREATED, {"customer_id": str(customer.id), "channel": message.channel})
        )
        return customer

    async def link_channel(self, customer_id: UUID, channel: str, external_id: str) -> Customer:
        customer = await self._follow(customer_id)
        return await self._link_or_merge(customer, channel, external_id)

    async def merge_customers(self, source_id: UUID, target_id: UUID) -> Customer:
        if source_id == target_id:
            found = await self.customers.get(target_id)
            if found is None:
                raise CustomerNotFound(f"customer {target_id} was not found")
            return found
        merged = await self.customers.merge(source_id, target_id)
        await self.events.publish(
            DomainEvent(
                CUSTOMER_MERGED,
                {"source_id": str(source_id), "target_id": str(merged.id)},
            )
        )
        return merged

    async def absorb_phone_from_text(self, customer: Customer, text: str) -> Customer:
        phones = find_phones(text)
        if not phones:
            return customer
        phone = phones[0]
        owner = await self.customers.get_by_phone(phone)
        if owner is not None and owner.id != customer.id:
            if customer.phone and customer.phone != phone:
                return customer
            return await self.merge_customers(customer.id, owner.id)
        if customer.phone is None:
            customer.phone = phone
            customer.updated_at = utcnow()
            return await self.customers.save(customer)
        return customer

    async def _follow(self, customer_id: UUID) -> Customer:
        customer = await self.customers.get(customer_id)
        if customer is None:
            raise CustomerNotFound(f"customer {customer_id} was not found")
        seen: set[UUID] = set()
        while customer.merged_into_id and customer.merged_into_id not in seen:
            seen.add(customer.id)
            nxt = await self.customers.get(customer.merged_into_id)
            if nxt is None:
                break
            customer = nxt
        return customer

    async def _link_or_merge(self, customer: Customer, channel: str, external_id: str) -> Customer:
        owner = await self.customers.get_by_channel(channel, external_id)
        if owner is None:
            await self.customers.link_channel(customer.id, channel, external_id)
            return customer
        owner = await self._follow(owner.id)
        if owner.id == customer.id:
            return customer
        survivor = customer if customer.phone else owner
        source = owner if survivor.id == customer.id else customer
        if survivor.phone and source.phone and survivor.phone != source.phone:
            raise InvalidMessage("channel is already linked to a different phone")
        return await self.merge_customers(source.id, survivor.id)
