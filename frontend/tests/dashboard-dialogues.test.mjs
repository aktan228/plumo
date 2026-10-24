import test from 'node:test';
import assert from 'node:assert/strict';
import {
  customerName, deliveryLabel, eventText, formatTime, initials, mergeMessages, modeLabel, replyHint, sendKey, textFits, textUsage,
} from '../src/features/dashboard/dialogue-model.ts';

const message = (id, timestamp, seq, extra = {}) => ({ id, seq, role: 'user', text: id, timestamp, author: null, event: null, unsupported: null, delivery: null, ...extra });

test('server pages merge by id and keep the server order', () => {
  const first = [message('a', '2026-10-14T08:00:00Z', 1), message('b', '2026-10-14T08:00:00Z', 2)];
  const newer = [message('b', '2026-10-14T08:00:00Z', 2, { text: 'b-updated' }), message('c', '2026-10-14T08:01:00Z', 3)];
  const merged = mergeMessages(first, newer);
  assert.deepEqual(merged.map(item => item.id), ['a', 'b', 'c']);
  assert.equal(merged[1].text, 'b-updated');
  // A late page of older messages lands before, not after.
  const older = mergeMessages(merged, [message('z', '2026-10-14T07:00:00Z', 0)]);
  assert.equal(older[0].id, 'z');
});

test('a retried send reuses its idempotency key; an edited text gets a new one', () => {
  let made = 0;
  const make = () => `key-${++made}`;
  const first = sendKey(undefined, 'Здравствуйте', make);
  assert.equal(sendKey(first, 'Здравствуйте', make).key, 'key-1');
  assert.equal(sendKey(first, 'Здравствуйте!', make).key, 'key-2');
});

test('channel limits: Telegram counts characters, Instagram counts UTF-8 bytes', () => {
  const telegram = { allowed: true, reason: null, max_chars: 4096, max_bytes: null, window_expires_at: null };
  const instagram = { allowed: true, reason: null, max_chars: null, max_bytes: 1000, window_expires_at: null };
  assert.equal(textFits(telegram, 'я'.repeat(4096)), true);
  assert.equal(textFits(telegram, 'я'.repeat(4097)), false);
  assert.equal(textFits(instagram, 'я'.repeat(500)), true);
  assert.equal(textFits(instagram, 'я'.repeat(501)), false);
  assert.equal(textUsage(instagram, 'ң'), '2/1000 B');
  assert.equal(textUsage(telegram, 'коротко'), null);
});

test('display never invents a customer and keeps Bishkek time', () => {
  const nobody = { id: '1', name: null, handle: null, phone: null, language: 'unknown' };
  assert.equal(customerName(nobody, 'telegram', 'ru'), 'Клиент Telegram');
  assert.equal(customerName({ ...nobody, handle: '@aigul' }, 'telegram', 'ru'), '@aigul');
  assert.equal(initials('Айгуль К.'), 'АК');
  // 08:30 UTC is 14:30 in Bishkek (UTC+6).
  assert.equal(formatTime('2026-10-14T08:30:00Z', 'ru', new Date('2026-10-14T10:00:00Z')), '14:30');
  assert.match(formatTime('2026-10-12T08:30:00Z', 'ru', new Date('2026-10-14T10:00:00Z')), /12.*14:30/);
});

test('statuses say what is known: accepted by the channel is not read by the customer', () => {
  assert.equal(deliveryLabel('sent', 'ru'), 'Принято каналом');
  assert.equal(deliveryLabel('unknown', 'en'), 'Status unknown');
  assert.equal(modeLabel('ai', 'ru', false), 'Автоответы выключены');
  assert.equal(modeLabel('human', 'en'), 'With a manager');
  assert.ok(replyHint({ allowed: false, reason: 'window_closed', max_chars: null, max_bytes: 1000, window_expires_at: null }, 'ru').includes('24 часов'));
  assert.equal(replyHint({ allowed: true, reason: null, max_chars: 4096, max_bytes: null, window_expires_at: null }, 'ru'), null);
  assert.equal(
    eventText(message('e', '2026-10-14T08:00:00Z', 5, { role: 'system', event: 'takeover', author: 'Азамат' }), 'ru'),
    'Менеджер взял диалог · автоматические ответы приостановлены · Азамат',
  );
});
