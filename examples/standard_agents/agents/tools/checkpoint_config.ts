// agents/tools/checkpoint_config.ts
import { z } from 'zod';
import { groundedTool } from '../../src/acs/grounded.js';
import { SETTINGS_PATH, fileAnchor, readSettings, writeText } from '../../src/example/settings.js';

/** The form of every restore point id this tool returns. */
export const CHECKPOINT_ID = /^cp-\d+$/;

export const checkpointPath = (id: string) => `/acs/checkpoints/${id}/settings.json`;

export default groundedTool({
  name: 'checkpoint_config',
  capability: 'checkpoint',
  domain: 'config',
  description: 'Save a restore point of the settings. Each change to the settings needs its own.',
  args: z.object({
    label: z.string().describe('Why the restore point is taken, e.g. "before raising the retry limit"'),
  }),
  execute: async (state, _args, call) => {
    const { text, sha256 } = await readSettings(state);
    const id = `cp-${call.seq}`;
    await writeText(state, checkpointPath(id), text);
    return {
      checkpoint_id: id,
      evidence_anchors: [fileAnchor(SETTINGS_PATH, sha256), fileAnchor(checkpointPath(id), sha256)],
    };
  },
});
