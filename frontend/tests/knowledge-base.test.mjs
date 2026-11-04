import test from 'node:test';
import assert from 'node:assert/strict';
import { materialIssue, updateMaterial } from '../src/features/dashboard/knowledge-model.ts';
import { restoredSnapshot, guestSnapshot, blankSnapshot } from '../src/features/create-agent/wizard-persistence.ts';
import { demoReply, emptyDraft } from '../src/features/create-agent/wizard-model.ts';
import { isAllowedRoute } from '../src/lib/api/routes.ts';

const source = { id: 'faq', kind: 'faq', title: 'Hours', question: 'When?', content: 'Nine to six.' };

test('editing at the ten-source limit replaces the item without duplicating it', () => {
  const sources = Array.from({ length: 10 }, (_, i) => ({ ...source, id: String(i) }));
  const edited = { ...sources[0], content: 'Updated hours.' };
  assert.equal(materialIssue(edited, sources), null);
  assert.equal(materialIssue({ ...source, id: 'new' }, sources), 'limits');
  const result = updateMaterial(sources, edited);
  assert.equal(result.length, 10);
  assert.equal(result[0].content, 'Updated hours.');
  assert.equal(sources[0].content, 'Nine to six.');
});

test('material validation counts UTF-8 bytes and rejects empty FAQ questions and unsafe links', () => {
  assert.equal(materialIssue({ ...source, content: 'я'.repeat(50001) }, []), 'limits');
  assert.equal(materialIssue({ ...source, question: ' ' }, []), 'question');
  assert.equal(materialIssue({ ...source, content: 'abc\0def' }, []), 'content');
  assert.equal(materialIssue({ ...source, kind: 'website', content: 'javascript:alert(1)' }, []), 'url');
});

test('disabled sources survive restoration and guest projection and do not answer in the demo', () => {
  const snapshot = { ...blankSnapshot(), sources: [{ ...source, enabled: false }] };
  const restored = restoredSnapshot({ data: snapshot, step: 0 });
  assert.equal(restored.sources[0].enabled, false);
  assert.equal(guestSnapshot(JSON.stringify(snapshot)).sources[0].enabled, false);
  assert.equal(guestSnapshot(JSON.stringify({ ...snapshot, sources: [{ ...source, enabled: 'false' }] })), null);
  assert.notEqual(demoReply('When?', { ...emptyDraft }, restored.sources).text, source.content);
});

test('browser access to published knowledge is read-only and cannot select another tenant', () => {
  assert.equal(isAllowedRoute('GET', 'knowledge'), true);
  for (const method of ['POST', 'PATCH', 'DELETE']) assert.equal(isAllowedRoute(method, 'knowledge'), false);
  assert.equal(isAllowedRoute('GET', 'knowledge/another-business'), false);
});
