// agents/tools/write_config.ts
import { z } from 'zod';
import { groundedTool } from '../../src/acs/grounded.js';
import { SETTINGS_PATH, fileAnchor, readSettings, writeText } from '../../src/example/settings.js';

// `mutate` is high risk in the ontology: it needs approval and a checkpoint.
// Nothing here says so; the wrapper takes both from the capability.
export default groundedTool({
  name: 'write_config',
  capability: 'mutate',
  domain: 'config',
  description:
    'Change one setting. A person must approve the exact change, and a restore point must have been saved first.',
  approval: { expires_ms: 15 * 60 * 1000 },
  args: z.object({
    key: z.string().min(1).describe('Setting name'),
    value: z.string().describe('New value'),
  }),
  execute: async (state, { key, value }) => {
    const before = await readSettings(state);
    const next = { ...before.settings, [key]: value };
    const sha256 = await writeText(state, SETTINGS_PATH, `${JSON.stringify(next, null, 2)}\n`);
    return {
      success: true,
      previous_state: before.settings,
      new_state: next,
      evidence_anchors: [fileAnchor(SETTINGS_PATH, before.sha256), fileAnchor(SETTINGS_PATH, sha256)],
    };
  },
});
