// agents/hooks/acs_audit_tool_calls.ts
import { defineHook } from '@standardagents/spec';
import { recordToolCall } from '../../src/acs/audit.js';

export default defineHook({
  hook: 'tool_call_done',
  id: 'acs_audit_tool_calls',
  execute: async (state, toolCall, toolResult) => {
    await recordToolCall(state, toolCall, toolResult, Date.now());
  },
});
