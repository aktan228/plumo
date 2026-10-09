import test from 'node:test';
import assert from 'node:assert/strict';
import { exampleConversations, updateConversations } from '../src/features/dashboard/dialogue-model.ts';

const message = { id: 'test-send', role: 'human', text: 'Уточняю варианты.', time: '12:00' };
const event = { id: 'handoff', role: 'event', text: 'Менеджер взял диалог', time: '12:00' };

test('sending requires the manager to own the conversation', () => {
  let conversations = exampleConversations(false);
  const count = conversations[0].messages.length;
  conversations = updateConversations(conversations, { type: 'send', id: conversations[0].id, message });
  assert.equal(conversations[0].messages.length, count);
  conversations = updateConversations(conversations, { type: 'mode', id: conversations[0].id, mode: 'human', event });
  conversations = updateConversations(conversations, { type: 'send', id: conversations[0].id, message });
  assert.equal(conversations[0].messages.at(-1).text, message.text);
  conversations = updateConversations(conversations, { type: 'mode', id: conversations[0].id, mode: 'ai', event: { ...event, id: 'return' } });
  const afterReturn = conversations[0].messages.length;
  conversations = updateConversations(conversations, { type: 'send', id: conversations[0].id, message: { ...message, id: 'late-send' } });
  assert.equal(conversations[0].messages.length, afterReturn);
});

test('handoff changes only the target conversation and repeated actions do not duplicate messages', () => {
  const initial = exampleConversations(false);
  const action = { type: 'mode', id: initial[0].id, mode: 'human', event };
  let conversations = updateConversations(initial, action);
  conversations = updateConversations(conversations, action);
  assert.equal(conversations[0].messages.length, initial[0].messages.length + 1);
  assert.equal(conversations[0].unread, 0);
  assert.equal(conversations[1], initial[1]);
  const send = { type: 'send', id: initial[0].id, message };
  conversations = updateConversations(updateConversations(conversations, send), send);
  assert.equal(conversations[0].messages.filter(item => item.id === message.id).length, 1);
  for (const text of ['   ', 'a'.repeat(2001)]) {
    const count = conversations[0].messages.length;
    conversations = updateConversations(conversations, { ...send, message: { ...message, id: 'invalid', text } });
    assert.equal(conversations[0].messages.length, count);
  }
});
