import test from 'node:test';
import assert from 'node:assert/strict';
import { initialWhatsAppDraft, canAdvanceWhatsApp, nextWhatsAppStep, previousWhatsAppStep } from '../src/features/dashboard/whatsapp-setup-model.ts';

test('phone flow requires a Business app number or a completed migration', () => {
  assert.equal(nextWhatsAppStep(0, initialWhatsAppDraft), 1);
  assert.equal(canAdvanceWhatsApp(1, initialWhatsAppDraft), false);
  assert.equal(nextWhatsAppStep(1, { ...initialWhatsAppDraft, app: 'personal' }), 1);
  assert.equal(nextWhatsAppStep(1, { ...initialWhatsAppDraft, app: 'personal', migrated: true }), 2);
  assert.equal(nextWhatsAppStep(1, { ...initialWhatsAppDraft, app: 'business' }), 2);
});

test('cloud flow skips the phone app step in both directions', () => {
  const draft = { ...initialWhatsAppDraft, method: 'cloud' };
  assert.equal(nextWhatsAppStep(0, draft), 2);
  assert.equal(previousWhatsAppStep(2, draft), 0);
  assert.equal(previousWhatsAppStep(2, initialWhatsAppDraft), 1);
});

test('payment selection is required and the connection step cannot advance', () => {
  assert.equal(nextWhatsAppStep(2, initialWhatsAppDraft), 2);
  for (const payment of ['meta', 'plumo']) assert.equal(nextWhatsAppStep(2, { ...initialWhatsAppDraft, payment }), 3);
  assert.equal(canAdvanceWhatsApp(3, { ...initialWhatsAppDraft, payment: 'meta' }), false);
});
