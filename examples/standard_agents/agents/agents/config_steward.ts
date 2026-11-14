// agents/agents/config_steward.ts
import { defineAgent } from '@standardagents/spec';

export default defineAgent({
  name: 'config_steward',
  title: 'Config steward',
  description: 'Changes settings only with a restore point and a recorded approval.',
  sideA: { prompt: 'config_steward', maxSteps: 12 },
  sideB: { human: true },
});
