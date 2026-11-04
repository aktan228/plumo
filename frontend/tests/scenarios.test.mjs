import test from 'node:test';
import assert from 'node:assert/strict';
import { blankSnapshot, guestSnapshot, restoredSnapshot } from '../src/features/create-agent/wizard-persistence.ts';
import { dashboardDestination, plannedSections } from '../src/features/dashboard/navigation.ts';
import { isAllowedRoute, forwardQuery } from '../src/lib/api/routes.ts';
import { validHandoffPhrases } from '../src/features/dashboard/scenario-model.ts';

test('literal phrase inputs reject unexecutable or oversized lines and accept Unicode', () => {
  assert.equal(validHandoffPhrases('атайын суроо\nХочу возврат'), true);
  assert.equal(validHandoffPhrases(''), true);
  for (const value of ['a', '..', 'ab\n'.repeat(11), 'x'.repeat(101)]) assert.equal(validHandoffPhrases(value), false);
});

test('scenario draft fields survive restore and old drafts default safely', () => {
  const snapshot = blankSnapshot();
  Object.assign(snapshot.settings, { qualificationPrompt: 'Выяснить район', openingQuestion: 'Как к вам обращаться?', handoffKeywords: 'хочу возврат' });
  assert.deepEqual(guestSnapshot(JSON.stringify(snapshot))?.settings, snapshot.settings);
  delete snapshot.settings.openingQuestion;
  assert.equal(restoredSnapshot({ step: 0, data: snapshot }).settings.openingQuestion, '');
  snapshot.settings.qualificationPrompt = 'x'.repeat(1501);
  assert.equal(guestSnapshot(JSON.stringify(snapshot)), null);
});
test('scenarios has a real destination and history is read-only through the BFF', () => {
  assert.equal(dashboardDestination('#scenarios'), 'scenarios');
  assert.equal(plannedSections.some(item => item.en === 'Scenarios'), false);
  assert.equal(isAllowedRoute('GET', 'scenarios'), true);
  for (const method of ['POST', 'PATCH', 'DELETE']) assert.equal(isAllowedRoute(method, 'scenarios'), false);
  assert.equal(forwardQuery(new URLSearchParams('before=4&business_id=other')), '?before=4');
});
