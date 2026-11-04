"""Real board counts, pagination, concurrent edits and independent conversation control."""
import asyncio
from uuid import uuid4

from sqlalchemy import func, select
from test_onboarding import wizard as wizard
from app.domain.models import utcnow
from app.infrastructure.database.models import CustomerRow, ConversationRow, MeetingRow, JobRow
from app.infrastructure.database.dialog_queries import encode_cursor


async def seed_board(wizard):
    ids = [uuid4() for _ in range(5)]
    now = utcnow()
    async with wizard.factory() as db:
        customer, other = uuid4(), uuid4()
        db.add_all([CustomerRow(id=customer, business_id=wizard.ids[0]), CustomerRow(id=other, business_id=wizard.ids[1])])
        await db.flush()
        for index, ident in enumerate(ids):
            db.add(ConversationRow(id=ident, business_id=wizard.ids[index == 4], customer_id=other if index == 4 else customer,
                channel="instagram" if index == 2 else "telegram", started_at=now,
                contact_name=["Айгуль ӨМҮР", "Other", "Name_100%", "Requested", "Private tenant B"][index],
                pipeline_stage="meeting_requested" if index == 3 else "unassigned",
                mode="human" if index == 1 else "ai", mode_version=7))
        await db.commit()
    return ids


async def column(wizard, **query):
    response = await wizard.http.get("/api/v1/dashboard/kanban", params={"stage": "unassigned", **query})
    assert response.status_code == 200, response.text
    return response.json()


async def move(wizard, ident, stage="new", version=0, **extra):
    return await wizard.http.patch(f"/api/v1/conversations/{ident}/stage", json={"stage": stage, "version": version, **extra})


async def test_columns_count_all_matches_before_cursor_and_filter_tenant(wizard):
    ids = await seed_board(wizard)
    first = await column(wizard, limit=2, business_id=str(wizard.ids[1]))
    assert first["total"] == 3 and len(first["items"]) == 2 and first["next_cursor"]
    second = await column(wizard, limit=2, cursor=first["next_cursor"])
    assert second["total"] == 3 and len(second["items"]) == 1 and second["next_cursor"] is None
    assert {item["id"] for item in first["items"] + second["items"]} == {str(ident) for ident in ids[:3]}
    assert (await column(wizard, channel="telegram"))["total"] == 2
    assert (await column(wizard, mode="human"))["items"][0]["id"] == str(ids[1])
    for query, ident in [("өмүр", ids[0]), ("_100%", ids[2])]:
        result = await column(wizard, q=query)
        assert result["total"] == 1 and result["items"][0]["id"] == str(ident)
    assert (await column(wizard, q="Private tenant B"))["total"] == 0
    from datetime import datetime, UTC
    exhausted = await column(wizard, cursor=encode_cursor(datetime(2000, 1, 1, tzinfo=UTC), uuid4()))
    assert exhausted["items"] == [] and exhausted["total"] == 3
    for params in [{"cursor": "!!"}, {"stage": "invalid"}, {"mode": "invalid"}, {"limit": 101}]:
        assert (await wizard.http.get("/api/v1/dashboard/kanban", params={"stage": "unassigned", **params})).status_code == 422


async def test_moves_persist_without_changing_mode_or_creating_actions(wizard):
    ids = await seed_board(wizard)
    response = await move(wizard, ids[1])
    assert response.status_code == 200 and response.json()["stage_version"] == 1
    assert (await column(wizard, stage="new"))["items"][0]["id"] == str(ids[1])
    assert (await column(wizard))["total"] == 2
    assert (await move(wizard, ids[1], version=0)).status_code == 409
    noop = await move(wizard, ids[1], version=1)
    assert noop.json()["stage_version"] == 1
    async with wizard.factory() as db:
        row = await db.get(ConversationRow, ids[1])
        assert row.mode == "human" and row.mode_version == 7
        assert row.pipeline_stage == "new" and row.stage_updated_by and row.stage_updated_at
        assert await db.scalar(select(func.count()).select_from(JobRow)) == 0


async def test_meeting_requires_confirmation_and_foreign_changes_are_refused(wizard):
    ids = await seed_board(wizard)
    assert (await move(wizard, ids[3], "meeting_confirmed")).status_code == 422
    assert (await move(wizard, ids[3], "meeting_confirmed", confirm_meeting=True)).status_code == 200
    async with wizard.factory() as db:
        assert await db.scalar(select(func.count()).select_from(MeetingRow)) == 0
    assert (await move(wizard, ids[4])).status_code == 404
    assert (await move(wizard, ids[0], business_id=str(wizard.ids[1]))).status_code == 422
    assert (await move(wizard, ids[0], version=True)).status_code == 422
    assert (await wizard.http.get("/api/v1/dashboard/kanban", params={"stage": "new"}, headers={"authorization": ""})).status_code == 401
    assert (await wizard.http.patch(f"/api/v1/conversations/{ids[0]}/stage", json={"stage": "new", "version": 0}, headers={"authorization": ""})).status_code == 401


async def test_concurrent_moves_have_one_winner(wizard):
    ids = await seed_board(wizard)
    responses = await asyncio.gather(move(wizard, ids[0], "new"), move(wizard, ids[0], "qualified"))
    assert sorted(response.status_code for response in responses) == [200, 409]
    async with wizard.factory() as db:
        row = await db.get(ConversationRow, ids[0])
        assert row.stage_version == 1 and row.mode == "ai" and row.mode_version == 7
