import test from 'node:test';
import assert from 'node:assert/strict';
import { isAllowedRoute, forwardQuery } from '../src/lib/api/routes.ts';
import { dashboardConversation, conversationHref } from '../src/features/dashboard/navigation.ts';
import { safeNextPath } from '../src/lib/auth/registration.ts';

const id = '12345678-1234-1234-1234-123456789abc';
test('manager proxy only allows scoped binding and manual notification actions', () => {
  assert.equal(isAllowedRoute('GET', 'manager-recipient'), true);
  for (const action of ['link','confirm','disconnect','cancel']) assert.equal(isAllowedRoute('POST', `manager-recipient/${action}`), true);
  assert.equal(isAllowedRoute('POST', `manager-recipient/notifications/${id}/resolve`), true);
  assert.equal(isAllowedRoute('GET', 'webhooks/manager-telegram'), false);
  assert.equal(isAllowedRoute('POST', 'webhooks/manager-telegram'), false);
  assert.equal(isAllowedRoute('PATCH', 'manager-recipient'), false);
  assert.equal(forwardQuery(new URLSearchParams('business_id=other&chat_id=999')), '');
});
test('a conversation link survives login and rejects malformed identifiers', () => {
  const href = conversationHref(id);
  assert.equal(dashboardConversation(new URL(href, 'https://example.test').search), id);
  assert.equal(safeNextPath(href), href);
  assert.equal(dashboardConversation('?conversation=../other'), null);
  assert.equal(conversationHref('https://evil.test'), '/dashboard#chats');
});
