// agents/tools/read_config.ts
import { z } from 'zod';
import { groundedTool } from '../../src/acs/grounded.js';
import { SETTINGS_PATH, fileAnchor, readSettings } from '../../src/example/settings.js';

export default groundedTool({
  name: 'read_config',
  capability: 'retrieve',
  domain: 'config',
  description: 'Read the current settings.',
  args: z.object({}),
  execute: async (state) => {
    const { settings, sha256 } = await readSettings(state);
    return {
      data: settings,
      evidence_anchors: [fileAnchor(SETTINGS_PATH, sha256)],
      confidence: 1,
    };
  },
});
