import test from 'node:test';
import assert from 'node:assert/strict';
import { isChangingManager, managerExplanation, managerStatusLabel, managerStatusTone } from '../src/features/dashboard/manager-notifications-model.ts';

const state = (extra = {}) => ({
  status: 'not_configured', recipient: null, candidate: null, attention: null,
  code_expires_at: null, bot_username: 'plumo_alerts_bot', service_bot_configured: true, ...extra,
});

test('without a recipient the dashboard says the external notification is not set up', () => {
  assert.equal(managerStatusLabel('not_configured', 'ru'), 'Не настроено');
  assert.match(managerExplanation(state(), 'ru'), /Внешнее уведомление не настроено/);
  assert.equal(managerStatusTone('not_configured'), 'idle');
});

test('every server state has its own text and tone', () => {
  for (const status of ['not_configured', 'waiting_code', 'awaiting_confirmation', 'ready', 'needs_attention']) {
    for (const locale of ['ru', 'en']) {
      assert.ok(managerStatusLabel(status, locale));
      assert.ok(managerExplanation(state({ status }), locale));
    }
  }
  assert.equal(managerStatusTone('ready'), 'ok');
  assert.equal(managerStatusTone('needs_attention'), 'error');
  assert.equal(managerStatusTone('awaiting_confirmation'), 'warn');
});

test('a change of manager is shown only while a new chat waits next to the confirmed one', () => {
  const chat = { label: 'Айбек @aibek_mgr', at: '2026-10-29T10:00:00Z' };
  assert.equal(isChangingManager(state({ status: 'ready', recipient: chat })), false);
  assert.equal(isChangingManager(state({ status: 'awaiting_confirmation', candidate: chat })), false);
  assert.equal(isChangingManager(state({ status: 'ready', recipient: chat, candidate: { ...chat, label: 'Новый' } })), true);
});
