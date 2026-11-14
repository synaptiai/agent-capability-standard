/**
 * The example as a packed agent: the entry point exports the Standard Agent
 * Specification's Packaging page describes, with every definition behind a
 * loader. A grounded agent ships like any other Standard Agent; its tools
 * carry their classification with them, and its approval endpoints and audit
 * hook travel in the same package.
 */
import type { PackedExports, PackedMeta } from '@standardagents/spec';

export const agents = {
  config_steward: async () => (await import('../agents/agents/config_steward.js')).default,
} satisfies PackedExports['agents'];

export const handlers = {} satisfies PackedExports['handlers'];

export const prompts = {
  config_steward: async () => (await import('../agents/prompts/config_steward.js')).default,
} satisfies PackedExports['prompts'];

export const tools = {
  read_config: async () => (await import('../agents/tools/read_config.js')).default,
  checkpoint_config: async () => (await import('../agents/tools/checkpoint_config.js')).default,
  write_config: async () => (await import('../agents/tools/write_config.js')).default,
  verify_config: async () => (await import('../agents/tools/verify_config.js')).default,
  rollback_config: async () => (await import('../agents/tools/rollback_config.js')).default,
} satisfies PackedExports['tools'];

export const models = {
  conversational: async () => (await import('../agents/models/conversational.js')).default,
} satisfies PackedExports['models'];

export const hooks = {
  acs_audit_tool_calls: async () => (await import('../agents/hooks/acs_audit_tool_calls.js')).default,
} satisfies PackedExports['hooks'];

export const threadEndpoints = {
  'acs/approvals.get': async () => (await import('../agents/api/acs/approvals.get.js')).default,
  'acs/approvals.post': async () => (await import('../agents/api/acs/approvals.post.js')).default,
} satisfies NonNullable<PackedExports['threadEndpoints']>;

export const __meta: PackedMeta = {
  packageId: 'standardagent-acs-config-steward',
  version: '0.0.0',
  entryAgents: ['config_steward'],
  packedAt: 0,
  description: 'Changes settings only with a restore point and a recorded approval.',
};
