/**
 * The binding as a safety layer (STANDARD 1.2.0 §5.18): control-only tools,
 * a tool's binding record in its annotation, R407 when the layer fails, an
 * output on the text-only result channel, and the offered-tool checks.
 */
import type { ThreadState } from '@standardagents/spec';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import checkpointConfig from '../agents/tools/checkpoint_config.js';
import readConfig from '../agents/tools/read_config.js';
import writeConfig from '../agents/tools/write_config.js';
import { acsAnnotation, acsControlAnnotation, controlTool, groundedTool, LAYER_NAME } from '../src/acs/grounded.js';
import { lintAgentBindings, lintPromptTools } from '../src/acs/lint.js';
import { STANDARD_VERSION } from '../src/acs/ontology.js';
import { KEYS, readTrace } from '../src/acs/records.js';
import { memoryThread } from './memory_thread.js';

const args = z.object({}).passthrough();

describe('control-only tools', () => {
  const done = controlTool({ name: 'done', description: 'Say the task is finished.', args });

  it('carry a control annotation and are never refused', async () => {
    expect(acsControlAnnotation(done)).toEqual({ standard: STANDARD_VERSION, ontology: '2.2.0', tool: 'done', control: true });
    expect(acsAnnotation(done)).toBeNull();
    const t = memoryThread();
    t.atRest();
    expect(await done.execute(t.state, {})).toEqual({ status: 'success', result: 'ok' });
    expect((await readTrace(t.state)).at(-1)).toMatchObject({ action: 'done', control: true, status: 'executed', capability: null });
  });

  it('still succeed when the record cannot be written, and report it', async () => {
    const failures: unknown[] = [];
    const tool = controlTool({ name: 'done', description: 'x', args, onRecordFailure: (e) => failures.push(e) });
    const t = memoryThread();
    const broken = new Proxy(t.state, {
      get(target, property, receiver) {
        if (property === 'setValue') return async () => Promise.reject(new Error('storage unavailable'));
        return Reflect.get(target, property, receiver) as unknown;
      },
    }) as ThreadState;
    expect((await tool.execute(broken, {})).status).toBe('success');
    expect(failures).toHaveLength(1);
  });

  it('may be bound to a stop action; a lint finds nothing', () => {
    const agent = { name: 'a', sideA: { prompt: 'p', stopTool: 'done' }, sideB: { human: true } } as const;
    expect(lintAgentBindings(agent, { done, read_config: readConfig })).toEqual([]);
  });

  it('may be invoked by a composite, whose flags it leaves as they are', () => {
    const composite = groundedTool({
      name: 'wrap_up',
      capability: 'invoke',
      invokes: { done } as never,
      description: 'x',
      args,
      execute: async () => ({ result: true, evidence_anchors: [] }),
    });
    expect(acsAnnotation(composite)).toMatchObject({ invokes: ['done'], risk: 'medium', requires_checkpoint: false, requires_approval: false });
  });
});

describe('the annotation is the tool binding record', () => {
  it('holds the declared members, the names invoked and the approval policy', () => {
    const apply = groundedTool({
      name: 'apply',
      capability: 'plan',
      additional_capabilities: ['mutate'],
      flags: { requires_approval: true },
      approval: { min_approvers: 2, role: 'ops', expires_ms: 3_600_000 },
      invokes: { write_config: writeConfig } as never,
      description: 'x',
      args,
      execute: async () => ({ steps: [], evidence_anchors: [], confidence: 1 }),
    });
    expect(acsAnnotation(apply)).toEqual({
      standard: STANDARD_VERSION,
      ontology: '2.2.0',
      tool: 'apply',
      capability: 'plan',
      layer: 'REASON',
      flags: { requires_approval: true },
      additional_capabilities: ['mutate'],
      invokes: ['write_config'],
      approval: { min_approvers: 2, role: 'ops', expires: '1h' },
      risk: 'high',
      mutation: true,
      requires_checkpoint: true,
      requires_approval: true,
    });
  });

  it('records the layer and a digest of its configuration on every entry', async () => {
    const t = memoryThread();
    await readConfig.execute(t.state, {});
    const entry = (await readTrace(t.state)).at(-1)!;
    expect(entry.recorded_by).toMatchObject({ name: LAYER_NAME, version: STANDARD_VERSION });
    expect(entry.recorded_by?.config_sha256).toMatch(/^[0-9a-f]{64}$/);
  });

  it('digests the checkpoint maximum age, which decides F501, with the annotation', async () => {
    const digestWith = async (checkpoint_max_age_ms?: number) => {
      const tool = groundedTool({
        name: 'look',
        capability: 'observe',
        description: 'x',
        args,
        ...(checkpoint_max_age_ms !== undefined ? { checkpoint_max_age_ms } : {}),
        execute: async () => ({ observation: true, evidence_anchors: [], confidence: 1 }),
      });
      const t = memoryThread();
      await tool.execute(t.state, {});
      return (await readTrace(t.state)).at(-1)!.recorded_by?.config_sha256;
    };
    const fiveMinutes = await digestWith(5 * 60 * 1000);
    expect(fiveMinutes).toMatch(/^[0-9a-f]{64}$/);
    expect(fiveMinutes).not.toBe(await digestWith());
    expect(await digestWith()).toBe(await digestWith(10 * 60 * 1000));
  });
});

describe('failure of the layer', () => {
  it('is R407 when the record of a call that ran cannot be completed', async () => {
    const t = memoryThread();
    t.files.set('/settings.json', '{}');
    let calls = 0;
    const flaky = new Proxy(t.state, {
      get(target, property, receiver) {
        if (property === 'setValue') {
          return async (key: string, value: unknown) => {
            // The started entry is written; the completion of it fails.
            if (key.startsWith('acs:trace:') && (value as { status?: string })?.status === 'executed') {
              calls += 1;
              throw new Error('storage unavailable');
            }
            return target.setValue(key, value);
          };
        }
        return Reflect.get(target, property, receiver) as unknown;
      },
    }) as ThreadState;
    const result = await readConfig.execute(flaky, {});
    expect(calls).toBe(1);
    expect(result).toMatchObject({ status: 'error', error_code: 'R407' });
  });

  it('is R402 for an output that breaks its contract, with a §9.8 diagnostic', async () => {
    const tool = groundedTool({
      name: 'big',
      capability: 'observe',
      description: 'x',
      args,
      execute: async () => ({ observation: 2 ** 53 + 2, evidence_anchors: [], confidence: 1 }),
    });
    const t = memoryThread();
    const result = await tool.execute(t.state, {});
    expect(result).toMatchObject({ status: 'error', error_code: 'R402', error_data: { code: 'R402', location: { tool: 'big', capability: 'observe' } } });
    expect((await readTrace(t.state)).at(-1)).toMatchObject({ status: 'failed', code: 'R402' });
  });

  it('returns the output as its I-JSON text', async () => {
    const t = memoryThread();
    t.files.set('/settings.json', '{"retries":"3"}');
    const result = await readConfig.execute(t.state, {});
    expect(result.status).toBe('success');
    expect(() => JSON.parse(result.result ?? '')).not.toThrow();
  });
});

describe('the offered-tool checks', () => {
  const tools = { checkpoint_config: checkpointConfig, write_config: writeConfig };

  it('count a host that takes checkpoints as performing checkpoint, and a classified tool only as its own capability', () => {
    const { checkpoint_config: _cp, ...withoutCheckpoint } = tools;
    expect(lintPromptTools('p', withoutCheckpoint).map((d) => d.code)).toEqual(['V102']);
    expect(lintPromptTools('p', withoutCheckpoint, { hostTakesCheckpoints: true })).toEqual([]);
    // The binding applies no classifier: a classified tool gets its worst
    // case and takes no checkpoint, whether or not it is shell-like.
    const batch = { annotations: { 'ai.synapti/acs': { standard: '1.2.0', ontology: '2.2.0', capability: 'mutate', classifier: 'batch' } } };
    expect(lintPromptTools('p', { ...withoutCheckpoint, batch }).map((d) => [d.code, d.location.tool])).toEqual([
      ['V102', 'write_config'],
      ['V102', 'batch'],
    ]);
  });

  it('report an unbound tool as W617 and keep KEYS intact', () => {
    expect(lintPromptTools('p', { ...tools, plain: {} }).map((d) => [d.code, d.name, d.location.tool])).toEqual([
      ['W617', 'UNBOUND_TOOL', 'plain'],
    ]);
    // A bare `acs` key is not this binding's key: the tool is unbound.
    const bare = { annotations: { acs: { standard: '1.2.0', ontology: '2.2.0', capability: 'retrieve' } } };
    expect(lintPromptTools('p', { ...tools, bare }).map((d) => [d.code, d.location.tool])).toEqual([['W617', 'bare']]);
    expect(KEYS.checkpoints).toBe('acs:checkpoints');
  });
});

