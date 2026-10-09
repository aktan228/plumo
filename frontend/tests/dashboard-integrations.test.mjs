import test from 'node:test';
import assert from 'node:assert/strict';
import { initialSetup, validSetup, setupStatus } from '../src/features/dashboard/integration-model.ts';

test('readiness requires access, authority and a method supported by this channel', () => {
  for (const channel of ['WhatsApp', 'Telegram', 'Instagram']) {
    const setup = initialSetup(channel);
    assert.equal(validSetup(channel, setup), false);
    assert.equal(validSetup(channel, { ...setup, access: true }), false);
    assert.equal(validSetup(channel, { ...setup, manager: true }), false);
    assert.equal(validSetup(channel, { ...setup, access: true, manager: true }), true);
    assert.equal(validSetup(channel, { method: 'unknown', access: true, manager: true }), false);
  }
  assert.equal(validSetup('Telegram', { method: 'cloud', access: true, manager: true }), false);
});

test('saved settings never claim that the provider is connected', () => {
  assert.equal(setupStatus(), 'not-connected');
  assert.equal(setupStatus({ ...initialSetup('WhatsApp'), access: true, manager: true }), 'needs-action');
});

test('only confirmed connection state overrides incomplete or saved setup', () => {
  assert.equal(setupStatus(undefined, true), 'connected');
  assert.equal(setupStatus(initialSetup('Telegram'), true), 'connected');
  assert.equal(setupStatus(initialSetup('Telegram'), false), 'needs-action');
});
