import test from 'node:test';
import assert from 'node:assert/strict';
import { forwardQuery, isAllowedRoute, isSameOriginWrite } from '../src/lib/api/routes.ts';
import { errorFrom } from '../src/lib/api/client.ts';
import { nextPollDelay } from '../src/lib/api/polling.ts';

const id = '3f2b8c1e-7d4a-4c1b-9e2f-0a1b2c3d4e5f';

test('the proxy only opens dashboard routes', () => {
  assert.equal(isAllowedRoute('GET', 'conversations'), true);
  assert.equal(isAllowedRoute('GET', `conversations/${id}`), true);
  assert.equal(isAllowedRoute('POST', `conversations/${id}/takeover`), true);
  assert.equal(isAllowedRoute('PATCH', `integrations/${id}`), true);
  const closed = [
    ['POST', 'messages'], ['POST', 'channels/telegram/events'], ['POST', 'auth/login'], ['GET', 'metrics'],
    ['POST', 'webhooks/telegram/x'], ['DELETE', `integrations/${id}`], ['GET', `conversations/${id}/../../messages`],
    ['GET', 'conversations/not-a-uuid'], ['POST', 'knowledge'],
  ];
  for (const [method, path] of closed) assert.equal(isAllowedRoute(method, path), false, `${method} ${path}`);
  assert.equal(forwardQuery(new URLSearchParams('q=цена&limit=30&business_id=x')), `?q=${encodeURIComponent('цена')}&limit=30`);
});

test('state changes need our origin and header', () => {
  assert.equal(isSameOriginWrite('GET', null, 'app.test', null), true);
  assert.equal(isSameOriginWrite('POST', 'https://app.test', 'app.test', '1'), true);
  assert.equal(isSameOriginWrite('POST', 'https://evil.test', 'app.test', '1'), false);
  assert.equal(isSameOriginWrite('POST', 'https://app.test', 'app.test', null), false);
  assert.equal(isSameOriginWrite('PATCH', null, 'app.test', '1'), false);
});

test('errors keep the server code and tell auth from outages', () => {
  const error = errorFrom(409, { error: 'mode_conflict', code: 'mode_conflict', message: 'take it', correlation_id: 'c-1' });
  assert.equal(error.code, 'mode_conflict');
  assert.equal(error.correlationId, 'c-1');
  assert.equal(errorFrom(401, {}).unauthenticated, true);
  assert.equal(errorFrom(0, null).unavailable, true);
  assert.equal(errorFrom(0, null).code, 'network_error');
  assert.equal(errorFrom(503, { code: 'backend_unavailable' }).unavailable, true);
});

test('polling backs off after failures and caps at a minute', () => {
  assert.equal(nextPollDelay(4000, 0), 4000);
  assert.equal(nextPollDelay(4000, 1), 8000);
  assert.equal(nextPollDelay(4000, 10), 60000);
});


test('test chat proxy only permits authenticated sandbox route shapes', () => {
  const ident = '12345678-1234-1234-1234-123456789abc';
  for (const [method, path] of [['GET', 'testing/sessions'], ['POST', 'testing/sessions'], ['GET', `testing/sessions/${ident}`], ['POST', `testing/sessions/${ident}/messages`]]) assert.equal(isAllowedRoute(method, path), true);
  for (const [method, path] of [['POST', `testing/sessions/${ident}`], ['GET', `testing/sessions/${ident}/messages`], ['PATCH', 'testing/sessions'], ['POST', 'messages'], ['GET', 'testing/sessions/not-an-id']]) assert.equal(isAllowedRoute(method, path), false);
});


test('readiness is read-only and Telegram verification uses scoped connection IDs', () => {
  const ident = '12345678-1234-1234-1234-123456789abc';
  assert.equal(isAllowedRoute('GET', 'dashboard/readiness'), true);
  assert.equal(isAllowedRoute('POST', 'dashboard/readiness'), false);
  assert.equal(isAllowedRoute('POST', `integrations/${ident}/verification`), true);
  assert.equal(isAllowedRoute('GET', `integrations/${ident}/verification`), false);
  assert.equal(isAllowedRoute('POST', 'integrations/other-business/verification'), false);
});
