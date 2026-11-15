// agents/models/conversational.ts
import { defineModel } from '@standardagents/spec';
import { openrouter } from '@standardagents/openrouter';

export default defineModel({
  name: 'conversational',
  provider: openrouter,
  model: 'anthropic/claude-sonnet-5',
});
