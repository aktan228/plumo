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

test('without prepared access the channel needs action, not a button that pretends to connect', () => {
  const noCredential = integration({ credentials: [] });
  assert.equal(cardStatus(noCredential), 'action_required');
  assert.equal(canConnect(noCredential), false);
  const noUrl = integration({ requirements: { public_url: false, secret_key: true } });
  assert.deepEqual(missingRequirements(noUrl), ['public_url']);
  assert.equal(canConnect(noUrl), false);
  assert.equal(canConnect(integration()), true);
  assert.equal(statusLabel('action_required', 'ru'), 'Требуется действие');
});
