import test from 'node:test';
import assert from 'node:assert/strict';
import { sourceUrl, sourceFits, demoReply, example, MAX_SOURCE_BYTES } from '../src/features/create-agent/wizard-model.ts';

test('sources accept web URLs but reject unsafe schemes and Instagram lookalikes', () => {
  assert.equal(sourceUrl('example.com'), 'https://example.com/');
  for (const value of ['javascript:alert(1)', 'https://user:secret@example.com', 'not a website']) assert.equal(sourceUrl(value), null);
  assert.equal(sourceUrl('instagram.com/business', true), 'https://instagram.com/business');
  assert.equal(sourceUrl('instagram.com.evil.example', true), null);
});

test('material limits count UTF-8 bytes and combined size', () => {
  const source = { id: '1', kind: 'text', title: 'test', content: 'я'.repeat(MAX_SOURCE_BYTES / 2) };
  assert.equal(sourceFits([], source), true);
  assert.equal(sourceFits([], { ...source, content: source.content + 'я' }), false);
  assert.equal(sourceFits([source, source], source), false);
  assert.equal(sourceFits(Array(10).fill({ ...source, content: 'a' }), { ...source, content: 'b' }), false);
});

test('chat uses only supplied approved answers and falls back for unknown facts', () => {
  const { draft, sources } = example('ru');
  assert.equal(demoReply('КАКИЕ квартиры есть?!', draft, sources).text, sources[0].content);
  assert.equal(demoReply(sources[0].question, draft, []).source, undefined);
  draft.fallback = 'Уточним у сотрудника.';
  assert.equal(demoReply('Сколько стоит квартира?', draft, sources).text, draft.fallback);
  assert.match(demoReply(sources[1].question, draft, sources).text, /запись не создана/);
});

test('explicit requests for a person pause the automated conversation', () => {
  const { draft, sources } = example('ru');
  for (const question of ['Позовите менеджера', 'Хочу поговорить с человеком', 'human please']) {
    assert.equal(demoReply(question, draft, sources).handoff, true);
  }
});
