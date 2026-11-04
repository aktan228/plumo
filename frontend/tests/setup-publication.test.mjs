import test from 'node:test';
import assert from 'node:assert/strict';
import { blankSnapshot } from '../src/features/create-agent/wizard-persistence.ts';
import { publicationGaps, setupCanPublish } from '../src/features/dashboard/setup-publication.ts';

function completeDraft() {
  const draft = blankSnapshot();
  Object.assign(draft.settings, { company: 'Example business', description: 'Approved services', greeting: 'Hello', goal: 'Answer questions', fallback: 'Ask a colleague' });
  draft.sources = [{ id: 'facts', kind: 'text', title: 'Facts', content: 'Approved facts.' }];
  return draft;
}

test('incomplete settings and missing materials prevent publication', () => {
  const blank = blankSnapshot();
  assert.equal(setupCanPublish(blank), false);
  assert.ok(publicationGaps(blank).fields.includes('company'));
  assert.equal(publicationGaps(blank).materials, true);
  const draft = completeDraft();
  assert.equal(setupCanPublish(draft), true);
  draft.settings.fallback = '   ';
  assert.equal(setupCanPublish(draft), false);
  assert.deepEqual(publicationGaps(draft).fields, ['fallback']);
});

test('pending wizard input prevents accidental publication of an unfinished source', () => {
  const draft = completeDraft();
  draft.entry.question = 'Unfinished question';
  assert.equal(publicationGaps(draft).pendingSource, true);
  assert.equal(setupCanPublish(draft), false);
  draft.entry.question = '  ';
  assert.equal(setupCanPublish(draft), true);
});

test('a disabled source can remain saved while optional settings are empty', () => {
  const draft = completeDraft();
  draft.sources[0].enabled = false;
  const before = JSON.stringify(draft);
  assert.equal(setupCanPublish(draft), true);
  assert.equal(JSON.stringify(draft), before);
  assert.equal(draft.settings.audience, '');
  assert.equal(draft.settings.handoffRules, '');
});
