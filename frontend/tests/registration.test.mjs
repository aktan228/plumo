import test from 'node:test';
import assert from 'node:assert/strict';
import { registrationIssue, safeNextPath, accountToken, passwordIssue } from '../src/lib/auth/registration.ts';

const valid = { name: '  Ак тан  ', email: ' CLIENT@EXAMPLE.COM ', password: 'A long password 123', locale: 'ru' };
test('registration accepts trimmed names, email and a passphrase', () => {
  assert.equal(registrationIssue(valid), null);
  for (const body of [null, [], { ...valid, name: '   ' }, { ...valid, name: 'a\0b' }, { ...valid, name: 'a'.repeat(101) }]) assert.equal(registrationIssue(body), 'name');
  assert.equal(registrationIssue({ ...valid, email: 'not-an-email' }), 'email');
  assert.equal(registrationIssue({ ...valid, locale: 'unexpected' }), 'locale');
});
test('registration password bounds count characters and reject whitespace-only input', () => {
  for (const password of ['short123', ' '.repeat(12), 'a'.repeat(129)]) assert.equal(registrationIssue({ ...valid, password }), 'password');
  for (const password of ['a'.repeat(10), 'a'.repeat(128), '🔑'.repeat(10)]) assert.equal(registrationIssue({ ...valid, password }), null);
  assert.equal(registrationIssue({ ...valid, password: '🔑'.repeat(5) }), 'password');
});
test('post-login redirects stay on this site, including backslash URLs', () => {
  for (const value of [null, 'https://evil.test', '//evil.test', '/\\evil.test', '/\t/evil.test']) assert.equal(safeNextPath(value), '/dashboard');
  assert.equal(safeNextPath('/dashboard#integrations'), '/dashboard#integrations');
  assert.equal(safeNextPath('/create/wizard?step=2'), '/create/wizard?step=2');
});

test('account links only read bounded URL-safe tokens from fragments', () => {
  const token = 'a'.repeat(43);
  assert.equal(accountToken('#token=' + token), token);
  for (const input of ['', '#token=short', '#token=' + 'a'.repeat(129), '#token=' + 'a'.repeat(42) + '%3C']) assert.equal(accountToken(input), null);
});
test('password recovery shares registration password rules', () => {
  assert.equal(passwordIssue('🔑'.repeat(10)), false);
  for (const value of [null, 'short', ' '.repeat(10), 'a'.repeat(129)]) assert.equal(passwordIssue(value), true);
});
