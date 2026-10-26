import test from 'node:test';
import assert from 'node:assert/strict';
import { blankSnapshot, snapshotBody, restoredSnapshot, guestSnapshot } from '../src/features/create-agent/wizard-persistence.ts';

test('server snapshots preserve the step, source text, logo, pending input and settings', () => {
  const draft=blankSnapshot();
  draft.step=3; draft.settings.company='QA Workspace'; draft.settings.logo='data:image/png;base64,aGVsbG8=';
  draft.sources=[{id:'1',kind:'file',title:'facts.md',content:'Материал'}];
  draft.entry={kind:'faq',value:'Draft answer',question:'Pending?'};
  const body=snapshotBody(draft,7);
  assert.deepEqual(restoredSnapshot({...body,business_id:'own',completed_at:null}),draft);
  assert.equal(body.version,7);
  assert.equal('business_id' in body,false);
});
test('guest drafts are bounded, typed and reject unsafe stored content', () => {
  const draft=blankSnapshot();
  assert.deepEqual(guestSnapshot(JSON.stringify(draft)),draft);
  for (const raw of [null,'invalid','null',JSON.stringify({...draft,step:6}),JSON.stringify({...draft,settings:{...draft.settings,logo:'javascript:evil'}}),JSON.stringify({...draft,sources:[{id:'1',kind:'instagram',title:'URL',content:'https://instagram.com.evil.example'}]})]) assert.equal(guestSnapshot(raw),null);
  draft.sources=[{id:'1',kind:'file',title:'facts.md',content:'я'.repeat(50001)}];
  assert.equal(guestSnapshot(JSON.stringify(draft)),null);
});
test('empty legacy server draft restores defaults without invented content', () => {
  assert.deepEqual(restoredSnapshot({data:null,step:0,version:0}),blankSnapshot());
});

test('guest transfer projects known fields and cannot inject tenant identity', () => {
  const draft=blankSnapshot();
  draft.settings.business_id='another-tenant'; draft.entry.business_id='another-tenant';
  draft.pricing={choice:'start',volume:1000,billing:'month',voice:false,business_id:'another-tenant'};
  const restored=guestSnapshot(JSON.stringify(draft));
  assert.ok(restored);
  assert.equal(JSON.stringify(restored).includes('business_id'),false);
});
