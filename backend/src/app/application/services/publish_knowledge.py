"""Replace only wizard-managed knowledge, preserving manual/imported facts of this business."""

from uuid import uuid5

from sqlalchemy import delete, select

from app.domain.models import utcnow
from app.infrastructure.database.models import KnowledgeItemRow

ORIGIN = "plumo-onboarding-v1"
CHUNK_CHARS = 2400


def source_chunks(content):
    text = content.strip()
    start = 0
    while start < len(text):
        stop = min(start + CHUNK_CHARS, len(text))
        if stop < len(text):
            boundary = text.rfind("\n", start + CHUNK_CHARS // 2, stop)
            if boundary > start:
                stop = boundary
        chunk = text[start:stop].strip()
        if chunk:
            yield chunk
        if stop == len(text):
            break
        start = max(start + 1, stop - 100)


async def publish_knowledge(session, business_id, data):
    await session.execute(
        delete(KnowledgeItemRow).where(
            KnowledgeItemRow.business_id == business_id,
            KnowledgeItemRow.metadata_json["origin"].astext == ORIGIN,
        )
    )
    existing = set(
        (await session.scalars(select(KnowledgeItemRow.title).where(KnowledgeItemRow.business_id == business_id))).all()
    )
    now = utcnow()
    count = 0
    for position, source in enumerate(data.sources, 1):
        # URLs are saved as references; no website fetching or invented website content.
        if source.kind not in ("text", "file", "faq"):
            continue
        for index, chunk in enumerate(source_chunks(source.content), 1):
            base = f"{source.title[:200]} · {position}.{index}"
            title = base
            suffix = 2
            while title in existing:
                title = f"{base} ({suffix})"
                suffix += 1
            existing.add(title)
            content = f"Вопрос: {source.question}\nОтвет: {chunk}" if source.kind == "faq" else chunk
            session.add(
                KnowledgeItemRow(
                    id=uuid5(business_id, f"{ORIGIN}:{source.id}:{index}"),
                    business_id=business_id,
                    category="faq" if source.kind == "faq" else "business_info",
                    title=title,
                    content=content,
                    metadata_json={
                        "origin": ORIGIN,
                        "source_id": source.id,
                        "source_kind": source.kind,
                        "source_title": source.title,
                        "chunk": index,
                        **({"question": source.question} if source.question else {}),
                    },
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            count += 1
    await session.flush()
    return count
