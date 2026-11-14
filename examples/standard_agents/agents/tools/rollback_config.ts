// agents/tools/rollback_config.ts
import { z } from 'zod';
import { groundedTool } from '../../src/acs/grounded.js';
import { SETTINGS_PATH, fileAnchor, readSettings, readText, writeText } from '../../src/example/settings.js';
import { checkpointPath } from './checkpoint_config.js';

export default groundedTool({
  name: 'rollback_config',
  capability: 'rollback',
  domain: 'config',
  description: 'Restore the settings to a saved restore point.',
  args: z.object({
    checkpoint_id: z.string().describe('The restore point to go back to, as checkpoint_config returned it'),
  }),
  execute: async (state, { checkpoint_id }) => {
    const saved = await readText(state, checkpointPath(checkpoint_id));
    if (saved === null) throw new Error(`there is no restore point '${checkpoint_id}'`);
    const before = await readSettings(state);
    const sha256 = await writeText(state, SETTINGS_PATH, saved);
    return {
      restored: true,
      previous_state: before.settings,
      restored_state: JSON.parse(saved),
      evidence_anchors: [fileAnchor(checkpointPath(checkpoint_id), sha256), fileAnchor(SETTINGS_PATH, sha256)],
    };
  },
});
