"""Customer profile and running summary. Separate from the business knowledge base."""

from app.domain.models import Customer, CustomerSummary, SummaryDraft, utcnow
from app.domain.ports import CustomerStore, SummaryStore


def read_unclear_count(facts: list[str] | None) -> int:
    for fact in facts or []:
        if fact.startswith("unclear_count:"):
            try:
                return int(fact.split(":", 1)[1])
            except ValueError:
                return 0
    return 0


def write_unclear_count(facts: list[str], count: int) -> list[str]:
    kept = [fact for fact in facts if not fact.startswith("unclear_count:")]
    kept.append(f"unclear_count:{count}")
    return kept


class MemoryService:
    def __init__(self, customers: CustomerStore, summaries: SummaryStore) -> None:
        self.customers = customers
        self.summaries = summaries

    async def get_summary(self, customer_id) -> CustomerSummary | None:
        return await self.summaries.get(customer_id)

    async def update_language(self, customer: Customer, language: str) -> Customer:
        if language in ("", "unknown") or language == customer.language:
            return customer
        if customer.language not in ("", "unknown") and customer.language != language:
            customer.language = "mixed"
        else:
            customer.language = language
        customer.updated_at = utcnow()
        return await self.customers.save(customer)

    async def mark_status(self, customer: Customer, status: str) -> Customer:
        if customer.status == status or customer.status == "merged":
            return customer
        customer.status = status
        customer.updated_at = utcnow()
        return await self.customers.save(customer)

    async def write_summary(
        self,
        customer: Customer,
        draft: SummaryDraft,
        language: str,
    ) -> CustomerSummary:
        """Persist the summary. A protected customer status is not downgraded by the draft."""

        now = utcnow()
        if customer.status == "new":
            customer.status = "active"
        if draft.need and draft.need != customer.need:
            customer.need = draft.need
        # update_language already folded this turn into the card (ru + ky -> mixed).
        # Overwriting with the turn language here would undo that every message.
        if customer.language in ("", "unknown") and language:
            customer.language = language
        customer.updated_at = now
        await self.customers.save(customer)
        record = CustomerSummary(
            customer_id=customer.id,
            summary=draft.summary,
            need=customer.need,
            language=customer.language,
            status=customer.status,
            important_facts=list(draft.important_facts),
            updated_at=now,
        )
        return await self.summaries.upsert(record)
