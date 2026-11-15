// agents/tools/rollback_config.ts
import { z } from 'zod';
import { groundedTool } from '../../src/acs/grounded.js';
import { readCheckpoints } from '../../src/acs/records.js';
import { SETTINGS_PATH, fileAnchor, parsedOrText, readText, writeText } from '../../src/example/settings.js';
import { CHECKPOINT_ID, checkpointPath } from './checkpoint_config.js';

// A rollback needs no approval, so the restore point it reads from is checked
// here: the id comes from the model and becomes part of a path.
export default groundedTool({
  name: 'rollback_config',
  capability: 'rollback',
  domain: 'config',
  description: 'Restore the settings to a saved restore point.',
  args: z.object({
    checkpoint_id: z
      .string()
      .regex(CHECKPOINT_ID)
      .describe('The restore point to go back to, as checkpoint_config returned it'),
  }),
  execute: async (state, { checkpoint_id }) => {
    const recorded = (await readCheckpoints(state)).some((c) => c.id === checkpoint_id);
    if (!CHECKPOINT_ID.test(checkpoint_id) || !recorded) {
      throw new Error(`'${checkpoint_id}' is not a restore point taken in this thread`);
    }
    const saved = await readText(state, checkpointPath(checkpoint_id));
    if (saved === null) throw new Error(`the restore point '${checkpoint_id}' has no saved settings`);
    // The current settings may be damaged, which is when a restore is needed,
    // so they are read as text and reported as text when they are not JSON.
    const before = (await readText(state, SETTINGS_PATH)) ?? '{}';
    const sha256 = await writeText(state, SETTINGS_PATH, saved);
    return {
      restored: true,
      previous_state: parsedOrText(before),
      restored_state: parsedOrText(saved),
      evidence_anchors: [fileAnchor(checkpointPath(checkpoint_id), sha256), fileAnchor(SETTINGS_PATH, sha256)],
    };
  },
});
