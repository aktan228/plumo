import test from 'node:test';
import assert from 'node:assert/strict';
import { eligibleVerification, newerIssue } from '../src/features/dashboard/improvement-model.ts';
import { improvementHref, testingHref, dashboardIssue, dashboardTest, dashboardDestination } from '../src/features/dashboard/navigation.ts';
import { isAllowedRoute, forwardQuery } from '../src/lib/api/routes.ts';

test('verification candidates require the corrected publication and a new session after the fix', () => {
  const fixed = '2026-11-04T08:00:00Z';
  assert.equal(eligibleVerification({ publication_version: 4, created_at: '2026-11-04T08:00:01Z' }, 4, fixed), true);
  assert.equal(eligibleVerification({ publication_version: 4, created_at: '2026-11-04T07:59:59Z' }, 4, fixed), false);
  assert.equal(eligibleVerification({ publication_version: 3, created_at: '2026-11-04T08:00:01Z' }, 4, fixed), false);
  assert.equal(eligibleVerification({ publication_version: 4, created_at: 'invalid' }, 4, fixed), false);
  assert.equal(eligibleVerification({ publication_version: 4, created_at: fixed }, null, null), false);
});
test('issue and test links use bounded UUIDs and a real dashboard destination', () => {
  const id = '11111111-1111-4111-8111-111111111111';
  assert.equal(improvementHref(id), `/dashboard?issue=${id}#improvements`);
  assert.equal(testingHref(id), `/dashboard?test=${id}#testing`);
  assert.equal(dashboardIssue(`?issue=${id}`), id);
  assert.equal(dashboardTest(`?test=${id}`), id);
  assert.equal(dashboardIssue('?issue=javascript:alert(1)'), null);
  assert.equal(improvementHref('../other'), '/dashboard#improvements');
  assert.equal(dashboardDestination('#improvements'), 'improvements');
});
test('improvement BFF writes are scoped; snapshots and tenant-wide endpoints are not exposed', () => {
  const id = '11111111-1111-4111-8111-111111111111';
  assert.equal(isAllowedRoute('POST', 'improvements'), true);
  assert.equal(isAllowedRoute('GET', `improvements/${id}`), true);
  assert.equal(isAllowedRoute('PATCH', `improvements/${id}`), true);
  assert.equal(isAllowedRoute('DELETE', `improvements/${id}`), false);
  assert.equal(isAllowedRoute('POST', `improvements/${id}/publish`), false);
  assert.equal(forwardQuery(new URLSearchParams('status=fixed&business_id=foreign')), '?status=fixed');
});
test('a late poll cannot undo a confirmed transition or a newer publication warning', () => {
  const current = { id: 'own', version: 3, current_publication_version: 5, status: 'verified' };
  assert.equal(newerIssue(current, { ...current, version: 2, status: 'fixed' }), current);
  assert.equal(newerIssue(current, { ...current, current_publication_version: 4 }), current);
  assert.equal(newerIssue(current, { ...current, version: 4, status: 'in_progress' }).status, 'in_progress');
  assert.equal(newerIssue(current, { ...current, id: 'other', version: 0 }).id, 'other');
});
