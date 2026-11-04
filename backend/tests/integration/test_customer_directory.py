"""Directory searches the full tenant and paginates without revealing foreign contacts."""
import base64
import json
from uuid import uuid4

from test_onboarding import wizard as wizard
from app.domain.models import utcnow
from app.infrastructure.database.models import CustomerRow, ConversationRow, CustomerChannelRow, MessageRow


async def directory(wizard, **params):
    response = await wizard.http.get("/api/v1/customers", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def seed_directory(wizard):
    ids = [uuid4() for _ in range(4)]
    now = utcnow()
    async with wizard.factory() as db:
        for index, ident in enumerate(ids):
            business = wizard.ids[0 if index < 3 else 1]
            db.add(CustomerRow(id=ident, business_id=business, phone=None,
                               contact_phone="+996555000111", language="ru", created_at=now))
        await db.flush()
        for index, ident in enumerate(ids):
            business = wizard.ids[0 if index < 3 else 1]
            channel = "instagram" if index == 2 else "telegram"
            db.add(ConversationRow(id=uuid4(), customer_id=ident, business_id=business, channel=channel,
                                   started_at=now, contact_name=["Айгуль ӨМҮР", "Name_100%", "Other contact", "Private tenant B"][index],
                                   contact_handle=f"@contact{index}"))
            db.add(CustomerChannelRow(id=uuid4(), customer_id=ident, business_id=business,
                                      channel=channel, external_id=f"external-{index}"))
        await db.commit()
    return ids


async def test_directory_pagination_filter_search_and_same_callback_number(wizard):
    ids = await seed_directory(wizard)
    first = await directory(wizard, limit=2)
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = await directory(wizard, limit=2, cursor=first["next_cursor"])
    found = [item["id"] for item in first["items"] + second["items"]]
    assert len(found) == len(set(found)) == 3
    assert set(found) == {str(ident) for ident in ids[:3]}
    assert second["next_cursor"] is None
    assert len((await directory(wizard, q="+996555000111"))["items"]) == 3
    assert [item["id"] for item in (await directory(wizard, channel="instagram"))["items"]] == [str(ids[2])]
    for query, expected in [("айгуль", ids[0]), ("өмүр", ids[0]), ("@contact1", ids[1]), ("external-2", ids[2]), ("_100%", ids[1])]:
        items = (await directory(wizard, q=query))["items"]
        assert [item["id"] for item in items] == [str(expected)], query
    card = (await wizard.http.get(f"/api/v1/customers/{ids[0]}")).json()
    assert card["name"] == "Айгуль ӨМҮР" and card["handle"] == "@contact0"
    assert card["channels"] == ["telegram"]
    assert (await directory(wizard, q="Private tenant B"))["items"] == []
    assert (await directory(wizard, channel="missing"))["items"] == []


async def test_directory_auth_scope_payload_and_foreign_card(wizard):
    ids = await seed_directory(wizard)
    assert (await wizard.http.get("/api/v1/customers", headers={"authorization": ""})).status_code == 401
    guessed = await directory(wizard, business_id=str(wizard.ids[1]))
    assert str(ids[3]) not in {item["id"] for item in guessed["items"]}
    foreign = {"authorization": f"Bearer {wizard.tokens[1]}"}
    other = (await wizard.http.get("/api/v1/customers", headers=foreign)).json()
    assert [item["id"] for item in other["items"]] == [str(ids[3])]
    for suffix in ["", "/history"]:
        assert (await wizard.http.get(f"/api/v1/customers/{ids[3]}{suffix}")).status_code == 404
    for cursor in ["broken", "!!", base64.urlsafe_b64encode(json.dumps(["2026-01-01", str(ids[0])]).encode()).decode(),
                   base64.urlsafe_b64encode(json.dumps(["2026-01-01T00:00:00+00:00", {}]).encode()).decode()]:
        assert (await wizard.http.get("/api/v1/customers", params={"cursor": cursor})).status_code == 422
    for params in [{"limit": 0}, {"limit": 101}, {"q": "x" * 101}]:
        assert (await wizard.http.get("/api/v1/customers", params=params)).status_code == 422


async def test_directory_does_not_search_or_display_cross_tenant_links(wizard):
    ids = await seed_directory(wizard)
    async with wizard.factory() as db:
        # Even corrupted links must not attach another business's data to an own card.
        db.add(CustomerChannelRow(id=uuid4(), customer_id=ids[0], business_id=wizard.ids[1],
                                  channel="voice", external_id="foreign-hidden"))
        foreign_dialog = uuid4()
        db.add(ConversationRow(id=foreign_dialog, customer_id=ids[0], business_id=wizard.ids[1], channel="voice",
                               started_at=utcnow(), contact_name="foreign-hidden"))
        await db.flush()
        db.add(MessageRow(id=uuid4(), conversation_id=foreign_dialog, customer_id=ids[0], role="user",
                          text="foreign-hidden", timestamp=utcnow(), metadata_json={}))
        await db.commit()
    assert (await directory(wizard, q="foreign-hidden"))["items"] == []
    assert (await directory(wizard, channel="voice"))["items"] == []
    assert all("voice" not in item["channels"] for item in (await directory(wizard))["items"])
    history = (await wizard.http.get(f"/api/v1/customers/{ids[0]}/history")).json()
    assert "foreign-hidden" not in json.dumps(history)
