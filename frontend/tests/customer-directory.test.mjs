import test from 'node:test';
import assert from 'node:assert/strict';
import { customerHref, dashboardCustomer, dashboardDestination } from '../src/features/dashboard/navigation.ts';
import { isAllowedRoute, forwardQuery } from '../src/lib/api/routes.ts';

test('customer list is read-only through the BFF and cannot pick another business', () => {
  assert.equal(isAllowedRoute('GET', 'customers'), true);
  assert.equal(isAllowedRoute('POST', 'customers'), false);
  assert.equal(isAllowedRoute('PATCH', 'customers'), false);
  assert.equal(forwardQuery(new URLSearchParams('q=contact&channel=telegram&limit=30&business_id=foreign')), '?q=contact&channel=telegram&limit=30');
});
test('customer links reopen the selected card and reject arbitrary identifiers', () => {
  const id = '11111111-1111-4111-8111-111111111111';
  assert.equal(customerHref(id), `/dashboard?customer=${id}#customers`);
  assert.equal(dashboardCustomer(`?customer=${id}`), id);
  assert.equal(dashboardDestination('#customers'), 'customers');
  assert.equal(customerHref('../foreign'), '/dashboard#customers');
  assert.equal(dashboardCustomer('?customer=javascript:alert(1)'), null);
});
