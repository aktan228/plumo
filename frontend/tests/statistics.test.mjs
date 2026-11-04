import test from 'node:test';
import assert from 'node:assert/strict';
import { statisticsPeriod, validStatisticsPeriod } from '../src/features/dashboard/statistics-model.ts';
import { isAllowedRoute, forwardQuery } from '../src/lib/api/routes.ts';
import { dashboardDestination } from '../src/features/dashboard/navigation.ts';

test('the default seven-day period follows Bishkek midnight across UTC dates', () => {
  assert.deepEqual(statisticsPeriod(new Date('2026-10-31T18:00:00Z')), { from: '2026-10-26', to: '2026-11-01' });
  assert.deepEqual(statisticsPeriod(new Date('2026-10-31T17:59:59Z')), { from: '2026-10-25', to: '2026-10-31' });
});
test('periods are ordered inclusive days, bounded and reject impossible dates', () => {
  assert.equal(validStatisticsPeriod('2026-11-01', '2026-11-01'), true);
  assert.equal(validStatisticsPeriod('2026-01-01', '2026-04-02'), true);
  for (const [start, end] of [['2026-01-01', '2026-04-03'], ['2026-11-02', '2026-11-01'], ['2026-02-30', '2026-03-01'], ['', '2026-11-01']]) {
    assert.equal(validStatisticsPeriod(start, end), false);
  }
});
test('statistics is read-only and only its date filters are forwarded, without a tenant selector', () => {
  assert.equal(isAllowedRoute('GET', 'dashboard/statistics'), true);
  assert.equal(isAllowedRoute('POST', 'dashboard/statistics'), false);
  assert.equal(forwardQuery(new URLSearchParams('date_from=2026-11-01&date_to=2026-11-02&business_id=foreign')), '?date_from=2026-11-01&date_to=2026-11-02');
  assert.equal(dashboardDestination('#statistics'), 'statistics');
});
