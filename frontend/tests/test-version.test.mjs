import test from 'node:test';
import assert from 'node:assert/strict';
import { testVersionState } from '../src/features/create-agent/test-version.ts';
import { knowledgeHref } from '../src/features/dashboard/navigation.ts';

test('an older test cannot represent the current publication and missing data is unknown', () => {
  assert.equal(testVersionState(3, 3), 'current');
  assert.equal(testVersionState(3, 4), 'stale');
  assert.equal(testVersionState(3, null), 'stale');
  assert.equal(testVersionState(3, undefined), 'unknown');
  assert.equal(testVersionState(undefined, 4), 'unknown');
});

test('source links carry only a valid material ID to the knowledge page', () => {
  const id = '11111111-1111-4111-8111-111111111111';
  assert.equal(knowledgeHref(id), `/dashboard?source=${id}#knowledge`);
  for (const value of ['../secret', 'javascript:alert(1)', 'bad&business_id=other']) {
    assert.equal(knowledgeHref(value), '/dashboard#knowledge');
  }
});
