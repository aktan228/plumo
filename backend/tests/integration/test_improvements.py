"""Tenant isolation and correction -> publication -> fresh reviewed evidence, using the real sandbox."""
import asyncio
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import func, select
from test_onboarding import wizard as wizard, payload
from test_published_agent import publish, core
from test_test_chat import start, send
from app.infrastructure.database.models import ImprovementRow, MessageRow, KnowledgeItemRow


async def report(wizard, session, request, ident=None, **extra):
    body = {"id": str(ident or uuid4()), "category": "incorrect_fact", "note": "Проверить часы работы",
            "test_session_id": str(session), "test_request_id": str(request), **extra}
    return await wizard.http.post("/api/v1/improvements", json=body)


async def transition(wizard, issue, status, note="", **extra):
    response = await wizard.http.patch(f"/api/v1/improvements/{issue['id']}",
        json={"version": issue["version"], "status": status, "note": note, **extra})
    return response


async def new_session(wizard):
    response = await wizard.http.post("/api/v1/testing/sessions", json={"id": str(uuid4())})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def test_correction_requires_publication_and_fresh_review_and_keeps_original_evidence(wizard):
    session = await start(wizard)
    turn = (await send(wizard, session)).json()
    assert turn["status"] == "succeeded" and turn["result"]["source_versions"]
    ident = uuid4()
    created = await report(wizard, session, turn["id"], ident)
    assert created.status_code == 200, created.text
    issue = created.json()
    original = issue["snapshot"]
    assert original["answer"] == turn["result"]["text"] and original["publication_version"] is not None
    async with wizard.factory() as db:
        recorded = original["source_versions"][0]
        material = await db.get(KnowledgeItemRow, UUID(recorded["id"]))
        assert recorded["content_sha256"] == sha256(material.content.encode()).hexdigest()
    replay = await report(wizard, session, turn["id"], ident)
    assert replay.json() == issue
    assert (await report(wizard, session, turn["id"], ident, note="Другой текст")).status_code == 409
    assert (await transition(wizard, issue, "verified", "Пропуск этапов")).status_code == 409
    response = await transition(wizard, issue, "in_progress")
    assert response.status_code == 200, response.text
    issue = response.json()
    assert (await transition(wizard, issue, "fixed", "Изменили часы")).status_code == 409
    body = payload()
    body["data"]["sources"][0]["content"] = "Работаем с 10 до 19."
    await publish(wizard, body)
    pre_fix_session = await new_session(wizard)
    fixed = await transition(wizard, issue, "fixed", "Опубликованы новые часы")
    assert fixed.status_code == 200, fixed.text
    issue = fixed.json()
    assert issue["snapshot"] == original
    assert issue["fixed_publication_version"] > original["publication_version"]
    old_turn = (await send(wizard, pre_fix_session)).json()
    assert (await transition(wizard, issue, "verified", "Проверка", test_session_id=pre_fix_session,
        test_request_id=old_turn["id"])).status_code == 409
    fresh_session = await new_session(wizard)
    fresh_turn = (await send(wizard, fresh_session)).json()
    assert fresh_turn["status"] == "succeeded"
    from app.infrastructure.database.models import TestSessionRow as SandboxSession, TestTurnRow as SandboxTurn
    foreign_session, foreign_request, failed_request = uuid4(), uuid4(), uuid4()
    async with wizard.factory() as db:
        db.add(SandboxSession(id=foreign_session, business_id=wizard.ids[1],
            publication_version=issue["fixed_publication_version"], state={}))
        await db.flush()
        db.add(SandboxTurn(session_id=foreign_session, request_id=foreign_request, text="private question",
            status="succeeded", result={"text": "private tenant evidence"}, day="2026-11-04"))
        db.add(SandboxTurn(session_id=UUID(fresh_session), request_id=failed_request, text="failed",
            status="failed", result={"text": "must not verify"}, day="2026-11-04"))
        await db.commit()
    refused = await transition(wizard, issue, "verified", "Review", test_session_id=str(foreign_session),
        test_request_id=str(foreign_request))
    assert refused.status_code == 409 and "private tenant evidence" not in refused.text
    assert (await transition(wizard, issue, "verified", "Review", test_session_id=fresh_session,
        test_request_id=str(failed_request))).status_code == 409
    assert (await transition(wizard, issue, "verified", test_session_id=fresh_session,
        test_request_id=fresh_turn["id"])).status_code == 409
    verified = await transition(wizard, issue, "verified", "Прочитал новый ответ, демопроверка пройдена",
        test_session_id=fresh_session, test_request_id=fresh_turn["id"])
    assert verified.status_code == 200, verified.text
    issue = verified.json()
    assert issue["verification_current"] is True and issue["verification"]["scope"] == "demo"
    assert issue["verification"]["answer"] == fresh_turn["result"]["text"]
    assert len(issue["history"]) == 4
    assert (await wizard.http.get("/api/v1/dashboard/readiness")).json()["quality_accepted"] is False
    await publish(wizard)
    stale = (await wizard.http.get(f"/api/v1/improvements/{issue['id']}")).json()
    assert stale["verification_current"] is False and stale["snapshot"] == original
    reopened = (await transition(wizard, stale, "in_progress")).json()
    assert reopened["verification"] is None and reopened["fixed_at"] is None
    assert reopened["history"][-2]["verification"]["test_request_id"] == fresh_turn["id"]


async def test_live_sources_preserve_versions_and_unknown_legacy_versions(wizard, settings, engine):
    await publish(wizard)
    answer = await core(wizard, settings, engine, "Когда открыты?")
    body = {"id": str(uuid4()), "category": "language_tone", "note": "Проверить формулировку", "message_id": str(answer.reply_message_id)}
    first = await wizard.http.post("/api/v1/improvements", json=body)
    assert first.status_code == 200, first.text
    snapshot = first.json()["snapshot"]
    assert snapshot["answer"] == answer.response_text and snapshot["publication_version"] is not None
    async with wizard.factory() as db:
        row = await db.get(MessageRow, answer.reply_message_id)
        row.metadata_json = {"model": "legacy-provider", "token": "must-not-appear-in-issue"}
        await db.commit()
    body["id"] = str(uuid4())
    legacy = await wizard.http.post("/api/v1/improvements", json=body)
    assert legacy.status_code == 200 and legacy.json()["snapshot"]["publication_version"] is None
    assert "must-not-appear" not in legacy.text
    preserved = (await wizard.http.get(f"/api/v1/improvements/{first.json()['id']}")).json()
    assert preserved["snapshot"] == snapshot


async def test_cross_tenant_sources_and_mutations_and_payloads_are_refused(wizard, settings, engine):
    own_session = await start(wizard)
    own_turn = (await send(wizard, own_session)).json()
    created = await report(wizard, own_session, own_turn["id"])
    issue = created.json()
    foreign = {"authorization": f"Bearer {wizard.tokens[1]}"}
    assert (await wizard.http.get("/api/v1/improvements", headers=foreign)).json()["items"] == []
    assert (await wizard.http.get(f"/api/v1/improvements/{issue['id']}", headers=foreign)).status_code == 404
    assert (await wizard.http.patch(f"/api/v1/improvements/{issue['id']}", headers=foreign,
        json={"version": 0, "status": "in_progress"})).status_code == 404
    assert (await wizard.http.post("/api/v1/improvements", headers=foreign, json={"id": str(uuid4()),
        "category": "incorrect_fact", "note": "source", "test_session_id": own_session,
        "test_request_id": own_turn["id"]})).status_code == 404
    await publish(wizard, index=1)
    other_answer = await core(wizard, settings, engine, "Когда открыты?", index=1, external="other-answer")
    assert (await wizard.http.post("/api/v1/improvements", json={"id": str(uuid4()), "category": "handoff", "note": "test",
        "message_id": str(other_answer.reply_message_id)})).status_code == 404
    assert (await wizard.http.get("/api/v1/improvements", params={"business_id": str(wizard.ids[1])})).json()["items"][0]["id"] == issue["id"]
    assert (await wizard.http.get("/api/v1/improvements", headers={"authorization": ""})).status_code == 401
    for extra in [{"note": " "}, {"category": "invalid"}, {"answer": "Injected answer"}, {"business_id": str(wizard.ids[1])}, {"message_id": str(uuid4())}]:
        assert (await report(wizard, own_session, own_turn["id"], **extra)).status_code == 422
    assert (await wizard.http.get("/api/v1/improvements", params={"cursor": "!!"})).status_code == 422
    assert (await wizard.http.get("/api/v1/improvements", params={"status": "invalid"})).status_code == 422


async def test_concurrent_create_and_transition_are_idempotent_or_conflict_and_pages_are_complete(wizard):
    session = await start(wizard)
    turn = (await send(wizard, session)).json()
    ident = uuid4()
    responses = await asyncio.gather(report(wizard, session, turn["id"], ident), report(wizard, session, turn["id"], ident))
    assert [response.status_code for response in responses] == [200, 200]
    issue = responses[0].json()
    changes = await asyncio.gather(transition(wizard, issue, "in_progress"), transition(wizard, issue, "in_progress"))
    assert sorted(response.status_code for response in changes) == [200, 409]
    for index in range(3):
        assert (await report(wizard, session, turn["id"], note=f"other {index}")).status_code == 200
    first = (await wizard.http.get("/api/v1/improvements", params={"limit": 2})).json()
    second = (await wizard.http.get("/api/v1/improvements", params={"limit": 2, "cursor": first["next_cursor"]})).json()
    assert len({row["id"] for row in first["items"] + second["items"]}) == 4 and second["next_cursor"] is None
    filtered = (await wizard.http.get("/api/v1/improvements", params={"status": "in_progress"})).json()
    assert [row["id"] for row in filtered["items"]] == [issue["id"]]
    async with wizard.factory() as db:
        assert await db.scalar(select(func.count()).select_from(ImprovementRow)) == 4


async def test_failed_test_answer_is_not_valid_source_or_verification(wizard):
    session = await start(wizard)
    request = uuid4()
    from app.infrastructure.database.models import TestTurnRow as SandboxTurn
    async with wizard.factory() as db:
        db.add(SandboxTurn(session_id=session, request_id=request, text="failed", status="failed", result={}, day="2026-11-04"))
        await db.commit()
    assert (await report(wizard, session, request)).status_code == 409
