import test from 'node:test';
import assert from 'node:assert/strict';
import { stages, moveCard, loadColumn } from '../src/features/dashboard/kanban-model.ts';
import { isAllowedRoute, forwardQuery } from '../src/lib/api/routes.ts';

test('optimistic moves preserve the rollback snapshot, mode and unrelated columns', () => {
  const card = { id: 'a', pipeline_stage: 'unassigned', stage_version: 2, mode: 'human' };
  const original = Object.fromEntries(stages.map(stage => [stage, { stage, total: stage === 'unassigned' ? 4 : 0, items: stage === 'unassigned' ? [card] : [], next_cursor: stage === 'unassigned' ? 'next' : null }]));
  const moved = moveCard(original, card, 'new');
  assert.equal(moved.unassigned.total, 3);
  assert.equal(moved.new.total, 1);
  assert.equal(moved.new.items[0].mode, 'human');
  assert.equal(moved.new.items[0].stage_version, 3);
  assert.equal(original.unassigned.total, 4);
  assert.deepEqual(original.unassigned.items, [card]);
  assert.equal(moved.qualified, original.qualified);
  assert.equal(moveCard(original, { ...card, stage_version: 1 }, 'new'), original);
});
test('loaded column windows retain full server counts and all cards beyond 100', async () => {
  const result = await loadColumn(150, async (limit, cursor) => {
    const offset = Number(cursor ?? 0);
    return { stage: 'new', total: 200, items: Array.from({ length: limit }, (_, i) => ({ id: String(offset + i) })), next_cursor: String(offset + limit) };
  });
  assert.equal(result.total, 200);
  assert.equal(result.items.length, 150);
  assert.equal(result.next_cursor, '150');
  await assert.rejects(loadColumn(100, async () => ({ stage: 'new', total: 100, items: [], next_cursor: 'same' })), /Repeated/);
});
test('the BFF only permits scoped column reads and versioned stage endpoint', () => {
  const id = '11111111-1111-4111-8111-111111111111';
  assert.equal(isAllowedRoute('GET', 'dashboard/kanban'), true);
  assert.equal(isAllowedRoute('PATCH', `conversations/${id}/stage`), true);
  assert.equal(isAllowedRoute('POST', `conversations/${id}/stage`), false);
  assert.equal(forwardQuery(new URLSearchParams('stage=new&mode=human&business_id=foreign')), '?stage=new&mode=human');
});
