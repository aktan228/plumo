"""Read-only customer directory, scoped before searching or paginating."""
import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from app.domain.errors import InvalidMessage
from app.infrastructure.database.dialog_queries import encode_cursor


async def customer_page(db, business_id, *, q=None, channel=None, cursor=None, limit=30, customer_id=None):
    params = {"business_id": business_id, "limit": limit + 1}
    where = ["c.business_id = :business_id", "c.merged_into_id IS NULL"]
    if customer_id:
        where.append("c.id = :customer_id")
        params["customer_id"] = customer_id
    if cursor:
        try:
            stamp, ident = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
            stamp, ident = datetime.fromisoformat(stamp), UUID(ident)
            if stamp.tzinfo is None:
                raise ValueError("timezone required")
        except (ValueError, TypeError, AttributeError, OverflowError, binascii.Error):
            raise InvalidMessage("cursor is invalid") from None
        where.append("(c.created_at, c.id) < (:stamp, :ident)")
        params.update(stamp=stamp, ident=ident)
    if channel:
        where.append("""(EXISTS (SELECT 1 FROM customer_channels cc WHERE cc.business_id=:business_id
            AND cc.customer_id=c.id AND cc.channel=:channel) OR EXISTS (SELECT 1 FROM conversations cv
            WHERE cv.business_id=:business_id AND cv.customer_id=c.id AND cv.channel=:channel))""")
        params["channel"] = channel
    if q and q.strip():
        # C-locale PostgreSQL does not case-fold Cyrillic. Support the product's RU/KY alphabets explicitly.
        def folded(column):
            return f"translate({column}, 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯҢӨҮ', 'абвгдеёжзийклмнопрстуфхцчшщъыьэюяңөү')"

        params["q"] = "%" + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append(f"""(c.phone ILIKE :q ESCAPE '\\' OR c.contact_phone ILIKE :q ESCAPE '\\'
            OR EXISTS (SELECT 1 FROM conversations cv WHERE cv.business_id=:business_id AND cv.customer_id=c.id
                AND ({folded('cv.contact_name')} ILIKE :q ESCAPE '\\' OR {folded('cv.contact_handle')} ILIKE :q ESCAPE '\\'))
            OR EXISTS (SELECT 1 FROM customer_channels cc WHERE cc.business_id=:business_id AND cc.customer_id=c.id
                AND {folded('cc.external_id')} ILIKE :q ESCAPE '\\'))""")
    sql = """SELECT c.id, c.phone, c.contact_phone, c.language, c.need, c.status, c.created_at,
        contact.contact_name AS name, contact.contact_handle AS handle,
        ARRAY(SELECT channel FROM (
            SELECT cc.channel FROM customer_channels cc WHERE cc.business_id=:business_id AND cc.customer_id=c.id
            UNION SELECT cv.channel FROM conversations cv WHERE cv.business_id=:business_id AND cv.customer_id=c.id
        ) channels ORDER BY channel) AS channels
        FROM customers c LEFT JOIN LATERAL (
            SELECT contact_name, contact_handle FROM conversations cv
            WHERE cv.customer_id=c.id AND cv.business_id=:business_id
                AND (NULLIF(cv.contact_name, '') IS NOT NULL OR NULLIF(cv.contact_handle, '') IS NOT NULL)
            ORDER BY cv.updated_at DESC, cv.id DESC LIMIT 1
        ) contact ON true WHERE """ + " AND ".join(where) + " ORDER BY c.created_at DESC, c.id DESC LIMIT :limit"
    rows = list((await db.execute(text(sql), params)).mappings())
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [dict(row) for row in rows],
            "next_cursor": encode_cursor(rows[-1]["created_at"], rows[-1]["id"]) if more else None}
