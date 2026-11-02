import test from 'node:test';
import assert from 'node:assert/strict';
import { canConnect, cardStatus, missingRequirements, statusLabel } from '../src/features/dashboard/integration-model.ts';

const integration = (extra = {}) => ({
  channel: 'telegram', status: 'not_connected', connection: null,
  credentials: [{ ref: 'tg-demo', label: 'Тестовый бот' }],
  requirements: { public_url: true, secret_key: true, credentials_file: true },
  webhook_url: null, ...extra,
});
const connection = status => ({ id: 'c1', channel: 'telegram', status, agent_enabled: false, account: { external_id: '1', display_name: 'Bot', username: 'bot', link: null }, last_error: null, details: {} });

test('a card is connected only when the server says so', () => {
  assert.equal(cardStatus(integration()), 'not_connected');
  assert.equal(cardStatus(integration({ connection: connection('connected') })), 'connected');
  assert.equal(cardStatus(integration({ connection: connection('error') })), 'error');
  assert.equal(cardStatus(integration({ connection: connection('disconnected') })), 'disconnected');
});

test('Telegram accepts a client token; Instagram still needs prepared access', () => {
  const noCredential = integration({ credentials: [] });
  assert.equal(cardStatus(noCredential), 'not_connected');
  assert.equal(canConnect(noCredential), true);
  assert.equal(canConnect(integration({ channel: 'instagram', credentials: [] })), false);
  const noUrl = integration({ requirements: { public_url: false, secret_key: true } });
  assert.deepEqual(missingRequirements(noUrl), ['public_url']);
  assert.equal(canConnect(noUrl), false);
  assert.equal(canConnect(integration()), true);
  assert.equal(statusLabel('action_required', 'ru'), 'Требуется действие');
});

test('the daily agent limit is shown as reached by calls or by money', async () => {
  const { limitReached, limitText } = await import('../src/features/dashboard/integration-model.ts');
  const limits = (extra = {}) => ({ day: '2026-11-02', calls: 5, calls_limit: 300, spent_usd: 0.1, limit_usd: 3, ...extra });
  assert.equal(limitReached(limits()), false);
  assert.equal(limitReached(limits({ calls: 300 })), true);
  assert.equal(limitReached(limits({ spent_usd: 3 })), true);
  assert.match(limitText(limits({ calls: 300 }), 'ru'), /исчерпан/);
  assert.match(limitText(limits(), 'ru'), /5 \/ 300/);
});
