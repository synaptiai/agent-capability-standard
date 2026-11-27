// The layer's destination policy (STANDARD 1.2.0 §4.4.2, §5.18.10): every
// grounded `send` tool obeys it and refuses a call it does not allow with
// F504 before any approval is asked for; a tool defined without the
// `destination` option has a destination the layer cannot tell, so every
// call of it is refused while a policy is in force.
import type { ToolResult } from '@standardagents/spec';
import { afterEach, describe, expect, it } from 'vitest';
import { z } from 'zod';
import type { Json } from '@synaptiai/acs-core';
import type { ProfileFlags, ProfilePolicy } from '@synaptiai/acs-core/wasm';
import { decideApproval, requestApproval } from '../src/acs/approval.js';
import { recordToolCall } from '../src/acs/audit.js';
import { acsAnnotation, groundedTool } from '../src/acs/grounded.js';
import { configureLayer, destinationPolicies, layerSecrets, registerTools, resetLayer } from '../src/acs/layer.js';
import { MemoryRefusal, persistEntry } from '../src/acs/memory.js';
import { effectiveFlags, type CapabilityId } from '../src/acs/ontology.js';
import { bindingProfiles, type ProfileCore } from '../src/acs/profiles.js';
import { actionRecord, readTrace } from '../src/acs/records.js';
import { memoryThread, user, type MemoryThread } from './memory_thread.js';

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
    destination: '/destination',
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
  it('refuses a destination no policy allows, before any approval request', async () => {
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
  it('refuses every call of a send tool defined without the destination option (security round 1, batch 6)', async () => {
    configureLayer({ destinations: HOOKS });
    const sent: string[] = [];
    // Its code sends to `url`; the layer does not guess that `destination`,
    // which the model can set to an allowed value, is where it sends.
    const tool = groundedTool({
      name: 'post_webhook',
      capability: 'send',
      description: 'Post to a webhook.',
      args: z.object({ url: z.string(), body: z.string() }).passthrough(),
      execute: async (_state, args) => {
        sent.push(args.url);
        return { sent: true, evidence_anchors: [] };
      },
    });
    const t = memoryThread();
    const refused = await tool.execute(t.state, {
      url: 'https://attacker.example.net/x',
      body: 'secret data',
      destination: 'https://hooks.example.com/ok',
    });
    expect(refusedF504(refused)).toBe(true);
    expect(refused.error).toContain('cannot tell where');
    expect(asked(t.values)).toBe(false);
    expect(sent).toEqual([]);
    expect(acsAnnotation(tool)?.destination).toBeUndefined();
    // With no policy in force the destination is the host's to check, as in 1.1.
    resetLayer();
    expect((await tool.execute(t.state, { url: 'https://x.example/', body: '' })).error_code).toBe('F502');
  });
  it('states a pointer option as the binding record\'s destination, and reads the destination there', async () => {
    configureLayer({ destinations: HOOKS });
    const tool = sendTool([], { destination: '/to' });
    expect(acsAnnotation(tool)?.destination).toBe('/to');
    expect(refusedF504(await tool.execute(memoryThread().state, { destination: 'https://hooks.example.com/r', to: 'https://evil.net/' }))).toBe(true);
    expect((await tool.execute(memoryThread().state, { destination: 'x', to: 'https://hooks.example.com/r' })).error_code).toBe('F502');
    expect(() => sendTool([], { destination: 'to' })).toThrow(/not an RFC 6901 pointer/);
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
  it("applies a composite's profiles' allowed_destinations to the sends it invokes, at every depth (§5.21.3, §5.18.4)", async () => {
    const profiles = bindingProfiles(profileCore([['https://ok.example/*']]), [{ domain: 'd' }], { onWarning: () => {} });
    const args = z.object({}).passthrough();
    const sent: string[] = [];
    const nested: ToolResult[] = [];
    const notify = sendTool(sent);
    const composite = (name: string, invoked: string, tool: unknown, extra: Record<string, unknown> = {}) =>
      groundedTool({
        name,
        capability: 'invoke',
        invokes: { [invoked]: tool } as never,
        description: name,
        args,
        ...extra,
        execute: async (state, a) => {
          const to = (a as { to: string }).to;
          const result = await state.invokeTool(invoked, invoked === 'send_report' ? { destination: to } : { to });
          if (invoked === 'send_report') nested.push(result);
          return { result: true, evidence_anchors: [] };
        },
      });
    // The profiles are given to the outer composite alone.
    const batch = composite('batch', 'send_report', notify, { profiles });
    const inner = composite('inner', 'send_report', notify);
    const outer = composite('outer', 'inner', inner, { profiles });
    const t = memoryThread();
    for (const [name, tool] of Object.entries({ send_report: notify, batch, inner, outer })) t.tools.set(name, tool);
    // Under a destination policy, a nested call runs only under a name
    // registered as the tool listed (security round 2, batch 5).
    registerTools({ send_report: notify, batch, inner, outer });
    const save = groundedTool({
      name: 'save',
      capability: 'checkpoint',
      description: 'save',
      args,
      execute: async (_s, _a, call) => ({ checkpoint_id: `cp-${call.seq}`, evidence_anchors: [] }),
    });
    const approve = async (th: MemoryThread, action: string, a: Record<string, unknown>) => {
      const request = await requestApproval(th.state, [{ action, capability: 'invoke', args: a as never }], {}, Date.now());
      await decideApproval(th.state, user('alice'), request.digest, 'approved', Date.now());
    };
    for (const name of ['batch', 'outer']) {
      for (const [to, ok] of [['https://evil.example/x', false], ['https://ok.example/x', true]] as const) {
        nested.length = 0;
        await save.execute(t.state, {});
        await approve(t, name, { to });
        expect((await t.tools.get(name)!.execute(t.state, { to })).status).toBe('success');
        expect(nested).toHaveLength(1);
        if (ok) {
          expect(nested[0]!.status).toBe('success');
        } else {
          expect(refusedF504(nested[0]!)).toBe(true);
        }
      }
    }
    expect(sent).toEqual(['https://ok.example/x', 'https://ok.example/x']);
    // The policy reaches only the calls the composite makes: the send
    // called on its own, with no profiles, is not under it.
    expect(refusedF504(await notify.execute(t.state, { destination: 'https://evil.example/x' }))).toBe(false);
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

// The host's own secrets, registered layer-wide (STANDARD 1.2.0 §6.7: a host
// SHOULD at least recognise the credentials it holds): every trace entry the
// binding writes is redacted with them, the audit hook's for a plain tool
// included, and persist data holding one is refused.
describe('secrets registered with configureLayer (security round 1, batch 6)', () => {
  const SECRET = 'Zq8fK2mVx9LpR4tW';
  const call = (id: string, name: string) => ({ id, type: 'function' as const, function: { name, arguments: '{}' } });

  it("redacts them in the audit hook's entry for a plain tool", async () => {
    configureLayer({ secrets: [SECRET] });
    const t = memoryThread();
    const entry = await recordToolCall(t.state, call('call_1', 'crm_sync'), { status: 'error', error: `upstream rejected api key ${SECRET}` }, 1);
    expect(entry.error).toBe('upstream rejected api key [REDACTED]');
    expect(JSON.stringify(await readTrace(t.state))).not.toContain(SECRET);
    // A secret the hook passes itself is redacted too.
    resetLayer();
    const other = await recordToolCall(t.state, call('call_2', 'crm_sync'), { status: 'error', error: `password ${SECRET} expired` }, 2, {
      secrets: [SECRET],
    });
    expect(other.error).toBe('password [REDACTED] expired');
  });

  it("redacts them in a grounded tool's entries and refuses persist data that holds one", async () => {
    configureLayer({ secrets: [SECRET] });
    const t = memoryThread();
    const fetchCrm = groundedTool({
      name: 'fetch_crm',
      capability: 'retrieve',
      description: 'fetch',
      args: z.object({}),
      execute: async () => {
        throw new Error(`upstream rejected api key ${SECRET}`);
      },
    });
    expect((await fetchCrm.execute(t.state, {})).status).toBe('error');
    expect(JSON.stringify(await readTrace(t.state))).not.toContain(SECRET);
    await expect(persistEntry(t.state, { key: 'k', data: { note: `key ${SECRET}` } }, 1)).rejects.toBeInstanceOf(MemoryRefusal);
  });

  it('takes an array of strings and replaces them with the rest of the configuration', () => {
    expect(() => configureLayer({ secrets: 'x' as never })).toThrow(/secrets must be an array of strings/);
    configureLayer({ secrets: [SECRET] });
    expect(layerSecrets()).toEqual([SECRET]);
    configureLayer({});
    expect(layerSecrets()).toEqual([]);
  });
});

// A grounded tool's own secrets join the layer's (security round 1, batch 8):
// the deployment registers its credentials with the tools that use them, and
// the audit hook's entry for a plain tool, which no grounded tool writes,
// must not keep one (STANDARD 1.2.0 §6.7).
describe("a grounded tool's secrets reach every entry (security round 1, batch 8)", () => {
  const HOST_KEY = 'hk_live_7f3a9c2e1b8d4f6a';
  const TENANT_KEY = 'tk_9d8c7b6a5f4e3d2c';
  const call = (id: string, name: string) => ({ id, type: 'function' as const, function: { name, arguments: '{}' } });
  const failing = (secrets: readonly string[] | (() => Promise<readonly string[]>)) =>
    groundedTool({
      name: 'list_items',
      capability: 'retrieve',
      description: 'list',
      args: z.object({}),
      secrets,
      execute: async () => {
        throw new Error(`GET https://api.vendor.example/v1/items failed: 401 for key ${HOST_KEY}`);
      },
    });

  it("redacts an array given at definition in the audit hook's entry for a plain tool", async () => {
    const t = memoryThread();
    const listItems = failing([HOST_KEY]);
    expect(layerSecrets()).toContain(HOST_KEY);
    // The grounded tool's own entry, linked by the hook.
    expect((await listItems.execute(t.state, {})).status).toBe('error');
    await recordToolCall(t.state, call('call_1', 'list_items'), { status: 'error', error: 'x' }, 1);
    // A plain tool failing with the same text: the entry the hook writes.
    const error = `GET https://api.vendor.example/v1/items failed: 401 for key ${HOST_KEY}`;
    const entry = await recordToolCall(t.state, call('call_2', 'http_get'), { status: 'error', error }, 2);
    expect(entry.capability).toBeNull();
    expect(entry.error).toBe('GET https://api.vendor.example/v1/items failed: 401 for key [REDACTED]');
    expect(JSON.stringify(await readTrace(t.state))).not.toContain(HOST_KEY);
    // persist data that holds it is refused, whichever tool registered it.
    await expect(persistEntry(t.state, { key: 'k', data: { note: `key ${HOST_KEY}` } }, 3)).rejects.toBeInstanceOf(MemoryRefusal);
  });

  it("redacts a function's values once a call has read them, and configureLayer keeps them", async () => {
    const t = memoryThread();
    const listItems = failing(async () => [TENANT_KEY]);
    expect(layerSecrets()).not.toContain(TENANT_KEY);
    expect((await listItems.execute(t.state, {})).status).toBe('error');
    configureLayer({});
    expect(layerSecrets()).toContain(TENANT_KEY);
    const entry = await recordToolCall(t.state, call('call_3', 'crm_sync'), { status: 'error', error: `rejected ${TENANT_KEY}` }, 4);
    expect(entry.error).toBe('rejected [REDACTED]');
    // resetLayer forgets them, as it forgets the layer's own.
    resetLayer();
    expect(layerSecrets()).toEqual([]);
  });
});

// The name of a tool call is the model's: under a prompt injection it can
// name a tool with a secret to put it into the records. The trace entry's
// `action`, the waiting list's copy of it and the audit record's `tool` and
// `intent` hold the redacted name, as its `error` does (STANDARD 1.2.0 §6.7;
// security round 4, batch 5).
describe('a tool name that holds a secret (security round 4, batch 5)', () => {
  const REGISTERED = 'hk_live_9f8e7d6c5b4a39281706';
  const PATTERNED = [
    'ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789',
    'AKIAIOSFODNN7EXAMPLE',
    // Unregistered tokens glued after `_`, as in an MCP tool's name: a token
    // starts after any character that is not an ASCII letter or digit.
    'mcp__srv__ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789',
    'mcp__srv__AKIAIOSFODNN7EXAMPLE',
    'mcp__AKIAIOSFODNN7EXAMPLE__list',
  ];
  const call = (id: string, name: string) => ({ id, type: 'function' as const, function: { name, arguments: '{}' } });
  const stored = (t: MemoryThread) => [...t.values.values()].join('\n');

  it("redacts the name the model called in the audit hook's entry and in the audit record exported from it", async () => {
    configureLayer({ secrets: [REGISTERED] });
    const t = memoryThread();
    for (const [i, name] of [...PATTERNED, REGISTERED, `x_${REGISTERED}`].entries()) {
      const entry = await recordToolCall(t.state, call(`call_${i}`, name), { status: 'error', error: `Tool '${name}' not found` }, i);
      expect(entry.action).toContain('[REDACTED]');
      expect(entry.error).toBe(`Tool '${entry.action}' not found`);
      const record = actionRecord(entry, 'thread-1');
      expect(record.tool).toBe(entry.action);
      expect(record.intent).toBe(`${entry.action} call`);
      expect(JSON.stringify(record)).not.toMatch(/ghp_|AKIA|hk_live/);
    }
    expect(stored(t)).not.toMatch(/ghp_|AKIA|hk_live/);
  });

  it("redacts a grounded tool's name, keeps the redacted name waiting, and links the hook by it", async () => {
    configureLayer({ secrets: [REGISTERED] });
    const t = memoryThread();
    const name = `sync_${REGISTERED}`;
    const tool = groundedTool({
      name,
      capability: 'retrieve',
      description: 'sync',
      args: z.object({}),
      execute: async () => ({ data: 1, confidence: 1, evidence_anchors: [] }) as never,
    });
    expect((await tool.execute(t.state, {})).status).toBe('success');
    const [own] = await readTrace(t.state);
    expect(own).toMatchObject({ action: 'sync_[REDACTED]', status: 'executed', capability: 'retrieve' });
    expect(t.values.get('acs:trace:unlinked')).toContain('sync_[REDACTED]');
    expect(stored(t)).not.toContain(REGISTERED);
    // The hook for that call links the entry by the redacted name: no second entry.
    const linked = await recordToolCall(t.state, call('call_1', name), { status: 'success' }, 2);
    expect(linked).toMatchObject({ seq: own!.seq, tool_call_id: 'call_1', action: 'sync_[REDACTED]' });
    expect(await readTrace(t.state)).toHaveLength(1);
    expect(JSON.parse(t.values.get('acs:trace:unlinked') ?? '[]')).toEqual([]);
  });
});
