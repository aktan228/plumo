import test from 'node:test';
import assert from 'node:assert/strict';
import { leadKey, leadPayload } from '../src/lib/leads.ts';

const form = (fields) => { const data = new FormData(); for (const [k, v] of Object.entries(fields)) data.set(k, v); return data; };

test('the form becomes a request without a mail client and keeps only known fields', () => {
  const payload = leadPayload(form({ name: '  Айжан   Т. ', company: 'Студия', email: ' Owner@Example.com ', message: 'Хотим пилот', business_id: 'x' }), 'wizard', 'ru', 'k'.repeat(32), 'Старт', 'Канал: Telegram');
  assert.deepEqual(Object.keys(payload).sort(), ['company', 'email', 'idempotency_key', 'locale', 'message', 'name', 'plan', 'source']);
  assert.equal(payload.name, 'Айжан Т.');
  assert.equal(payload.email, 'owner@example.com');
  assert.equal(payload.message, 'Хотим пилот\n\nКанал: Telegram');
  assert.ok(payload.message.length <= 2000);
});

test('a key fits the backend format', () => {
  assert.match(leadKey(), /^[A-Za-z0-9_-]{16,64}$/);
  assert.notEqual(leadKey(), leadKey());
});
