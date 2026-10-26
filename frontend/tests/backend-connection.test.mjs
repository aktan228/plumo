import test from 'node:test';
import assert from 'node:assert/strict';
import { backendConnection, connectionFailure } from '../src/lib/server/backend-connection.ts';

test('pasted whitespace is removed without changing the actual backend or key', () => {
  assert.deepEqual(backendConnection('  https://api.example.com/\r\n', ' example-key\n', true), { base: 'https://api.example.com', key: 'example-key' });
  assert.equal(backendConnection(undefined, undefined, false).base, 'http://127.0.0.1:8000');
});

test('deployment config errors are categorized without leaking config values', () => {
  for (const [url, key, reason] of [
    [undefined, undefined, 'backend_url_missing'],
    ['http://127.0.0.1:8000', undefined, 'backend_url_local'],
    ['https://user:secret@api.example.com', undefined, 'backend_url_invalid'],
    ['"https://api.example.com"', undefined, 'backend_url_invalid'],
    ['https://api.example.com', 'secret\nvalue', 'backend_key_invalid'],
  ]) {
    assert.throws(() => backendConnection(url, key, true), error => error.message === reason && connectionFailure(error) === reason);
  }
});

test('nested fetch failures distinguish DNS, timeout, refused connection and TLS', () => {
  for (const [code, reason] of [['ENOTFOUND', 'backend_dns_error'], ['UND_ERR_CONNECT_TIMEOUT', 'backend_timeout'], ['ECONNREFUSED', 'backend_connection_refused'], ['ERR_TLS_CERT_ALTNAME_INVALID', 'backend_tls_error']]) {
    assert.equal(connectionFailure({ cause: { code, message: 'secret in raw error' } }), reason);
  }
  assert.equal(connectionFailure({ name: 'TimeoutError' }), 'backend_timeout');
  assert.equal(connectionFailure(new Error('secret')), 'backend_network_error');
});
