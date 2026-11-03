"""The worker commits the stored customer message before asking the model (README, "Надёжность ядра")."""

from sqlalchemy import text

from app.domain.models import ExtractedCustomerData, LLMGeneration, SummaryDraft


class Watching:
    """Model fake: records whether a transaction was open in Postgres while it was asked."""

    def __init__(self, stand, fail_first: bool = False):
        self.stand, self.fail_first, self.open_during_call = stand, fail_first, []

    async def generate_response(self, context, route):
        async with self.stand.factory() as probe:
            # Any other connection idle in a transaction holds locks and a pool slot during the call.
            open_tx = await probe.scalar(
                text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state LIKE 'idle in transaction%'")
            )
        self.open_during_call.append(open_tx)
        if self.fail_first:
            self.fail_first = False
            raise RuntimeError("worker died while the model was thinking")
        return LLMGeneration("Квартира на Чуй стоит 85 000 USD.", [], False, None, 0.9, "watching", 1, 1, 0.0)

    async def extract_customer_data(self, text):
        return ExtractedCustomerData()

    async def summarize(self, messages, previous):
        return SummaryDraft("-", None, [], None)

    async def classify(self, text, labels):
        return labels[0]


async def test_no_transaction_is_open_while_the_model_answers(stand, monkeypatch):
    model = Watching(stand)
    monkeypatch.setattr(stand.runtime.providers, "llm", lambda name: model)
    connection = await stand.telegram()
    await stand.tg_update(connection, 1, "Сколько стоит квартира на Чуй?")
    await stand.worker.drain()
    assert model.open_during_call == [0]
    assert len(stand.providers.sent) == 1


async def test_a_turn_cut_off_during_the_model_call_is_finished_by_the_retry(stand, monkeypatch):
    model = Watching(stand, fail_first=True)
    monkeypatch.setattr(stand.runtime.providers, "llm", lambda name: model)
    connection = await stand.telegram()
    await stand.tg_update(connection, 1, "Сколько стоит квартира на Чуй?")
    await stand.worker.drain()
    assert stand.providers.sent == []
    # The customer's message is kept although the turn failed.
    assert (await stand.sql("SELECT count(*) FROM messages WHERE role = 'user'"))[0][0] == 1

    await stand.sql("UPDATE jobs SET run_at = now() WHERE status = 'queued'")
    await stand.worker.drain()
    assert len(stand.providers.sent) == 1 and "85 000" in stand.providers.sent[0]["text"]
    assert (await stand.sql("SELECT count(*) FROM messages WHERE role = 'user'"))[0][0] == 1
    assert (await stand.sql("SELECT count(*) FROM messages WHERE role = 'assistant'"))[0][0] == 1
