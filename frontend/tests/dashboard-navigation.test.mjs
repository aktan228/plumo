import test from 'node:test';
import assert from 'node:assert/strict';
import { dashboardDestination, dashboardGroups } from '../src/features/dashboard/navigation.ts';

test('dashboard entry and all working hash links resolve consistently', () => {
  assert.equal(dashboardDestination(''), 'chats');
  for (const view of ['chats', 'knowledge', 'settings', 'testing', 'integrations', 'customers', 'statistics', 'improvements', 'help']) {
    assert.equal(dashboardDestination(`#${view}`), view);
  }
  for (const group of dashboardGroups) {
    for (const item of group.items) {
      assert.equal(dashboardDestination(`#${item.id}`), item.href.startsWith('#') ? item.id : 'wizard');
    }
  }
});

test('settings and knowledge links stay in the dashboard; unfinished sections open guidance', () => {
  assert.equal(dashboardDestination('#settings'), 'settings');
  assert.equal(dashboardDestination('#knowledge'), 'knowledge');
  for (const section of ['voice', 'broadcasts', 'unknown']) {
    assert.equal(dashboardDestination(`#${section}`), 'help');
  }
});

test('the skip link preserves the current dashboard section', () => {
  assert.equal(dashboardDestination('#workspace'), null);
});
