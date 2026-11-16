// The layer's destination policy (STANDARD 1.2.0 §4.4.2, §5.18.10): every
// grounded `send` tool obeys it, whether or not it was defined with the
// `destination` option, and refuses a call it does not allow with F504
// before any approval is asked for.
import type { ToolResult } from '@standardagents/spec';
import { afterEach, describe, expect, it } from 'vitest';
import { z } from 'zod';
import type { Json } from '@synaptiai/acs-core';
import type { ProfileFlags, ProfilePolicy } from '@synaptiai/acs-core/wasm';
import { groundedTool } from '../src/acs/grounded.js';
import { configureLayer, destinationPolicies, resetLayer } from '../src/acs/layer.js';
import { effectiveFlags, type CapabilityId } from '../src/acs/ontology.js';
import { bindingProfiles, type ProfileCore } from '../src/acs/profiles.js';
import { memoryThread } from './memory_thread.js';

const HOOKS = [['https://hooks.example.com/*']];
const NO_RULES: ProfilePolicy = { minimum_confidence: null, grounding: [], destinations: [], trust_weights: {} };

function profileCore(destinations: string[][]): ProfileCore {
  return {
    checkProfiles: () => ({ diagnostics: [], suggestions: [] }),
    profileFlags: (_p: Json[], c: CapabilityId): ProfileFlags => ({ ...effectiveFlags(c).flags, person: false }),
    profilePolicy: () => ({ ...NO_RULES, destinations }),
  };
}

const sendTool = (sent: string[], extra: Record<string, unknown> = {}) =>
  groundedTool({
    name: 'send_report',
    capability: 'send',
    description: 'Send the report.',
    args: z.object({ destination: z.unknown(), to: z.string().optional() }),
    ...extra,
    execute: async (_state, args) => {
      sent.push(String(args.destination ?? args.to));
      return { sent: true, evidence_anchors: [] };
    },
  });

const refusedF504 = (r: ToolResult) => r.status === 'error' && r.error_code === 'F504';

/** Whether the thread holds an approval request. */
const asked = (values: Map<string, string>) => [...values.keys()].some((k) => k.startsWith('acs:approval'));

afterEach(() => resetLayer());

describe('configureLayer', () => {
  it('refuses a send tool defined without the option, before any approval request', async () => {
    configureLayer({ destinations: HOOKS });
    const sent: string[] = [];
    const tool = sendTool(sent);
    const t = memoryThread();
    const refused = await tool.execute(t.state, { destination: 'https://evil.net/x' });
    expect(refusedF504(refused)).toBe(true);
    expect(refused.error).toContain("destination is not one the destination policies in force allow");
    expect(refused.error).not.toContain('evil.net');
    expect(asked(t.values)).toBe(false);
    // An allowed destination goes on to the approval the send needs.
    const ok = await tool.execute(t.state, { destination: 'https://hooks.example.com/r' });
    expect(ok.error_code).not.toBe('F504');
    expect(asked(t.values)).toBe(true);
    expect(sent).toEqual([]);
  });
  it('refuses a destination that is not a string', async () => {
    configureLayer({ destinations: HOOKS });
    const result = await sendTool([]).execute(memoryThread().state, { destination: { url: 'x' } });
    expect(refusedF504(result)).toBe(true);
    expect(result.error).toContain('not a string');
  });
  it('reads the destination where the option says', async () => {
    configureLayer({ destinations: HOOKS });
    const tool = sendTool([], { destination: (a: Record<string, unknown>) => a['to'] });
    const result = await tool.execute(memoryThread().state, { destination: 'https://hooks.example.com/r', to: 'https://evil.net/' });
    expect(refusedF504(result)).toBe(true);
  });
  it("applies a profile policy with no host policy (the core's profilePolicy)", async () => {
    configureLayer({ profilePolicy: { destinations: HOOKS } });
    expect(destinationPolicies()).toEqual(HOOKS);
    expect(refusedF504(await sendTool([]).execute(memoryThread().state, { destination: 'https://evil.net/x' }))).toBe(true);
  });
  it("applies a tool's own profiles' allowed_destinations (§5.21.3)", async () => {
    for (const destinations of [[['mailto:*']], [[]]]) {
      const profiles = bindingProfiles(profileCore(destinations), [{ domain: 'd' }], { onWarning: () => {} });
      const result = await sendTool([], { profiles }).execute(memoryThread().state, { destination: 'https://x.example/' });
      expect(refusedF504(result)).toBe(true);
    }
  });
  it('throws on an invalid pattern, keeping the earlier configuration', () => {
    configureLayer({ destinations: HOOKS });
    expect(() => configureLayer({ destinations: [['https://hooks.example.com:*']] })).toThrow(/policy 0, pattern 0/);
    expect(destinationPolicies()).toEqual(HOOKS);
  });
  it('checks nothing after resetLayer', async () => {
    configureLayer({ destinations: HOOKS });
    resetLayer();
    const result = await sendTool([]).execute(memoryThread().state, { destination: 'https://evil.net/x' });
    expect(result.error_code).not.toBe('F504');
  });
  it('throws for the option on a tool that does not send', () => {
    expect(() =>
      groundedTool({
        name: 'read',
        capability: 'retrieve',
        description: 'd',
        args: z.object({}),
        destination: () => 'x',
        execute: async () => ({ data: 1, confidence: 1, evidence_anchors: [] }) as never,
      }),
    ).toThrow(/destination option is for a tool that performs send/);
  });
});
