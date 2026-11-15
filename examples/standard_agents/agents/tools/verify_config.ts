// agents/tools/verify_config.ts
import { z } from 'zod';
import { groundedTool } from '../../src/acs/grounded.js';
import { SETTINGS_PATH, fileAnchor, readSettings } from '../../src/example/settings.js';

export default groundedTool({
  name: 'verify_config',
  capability: 'verify',
  domain: 'config',
  description: 'Check that a setting has the expected value.',
  args: z.object({
    key: z.string().min(1).describe('Setting name'),
    expected: z.string().describe('The value it should have'),
  }),
  execute: async (state, { key, expected }) => {
    const { settings, sha256 } = await readSettings(state);
    const actual = settings[key] ?? null;
    const passed = actual === expected;
    return {
      passed,
      results: [{ condition: `${key} == ${JSON.stringify(expected)}`, passed, actual }],
      violations: passed ? [] : [`${key} is ${JSON.stringify(actual)}`],
      evidence_anchors: [fileAnchor(SETTINGS_PATH, sha256)],
      confidence: 1,
    };
  },
});
