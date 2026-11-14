import { validateAgentDefinition, type HookToolCall, type PackedExports, type ToolResult } from '@standardagents/spec';
import { Ajv2020 } from 'ajv/dist/2020.js';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import approvalsGet from '../agents/api/acs/approvals.get.js';
import approvalsPost from '../agents/api/acs/approvals.post.js';
import configSteward from '../agents/agents/config_steward.js';
import auditHook from '../agents/hooks/acs_audit_tool_calls.js';
import prompt from '../agents/prompts/config_steward.js';
import checkpointConfig from '../agents/tools/checkpoint_config.js';
import readConfig from '../agents/tools/read_config.js';
import rollbackConfig from '../agents/tools/rollback_config.js';
import verifyConfig from '../agents/tools/verify_config.js';
import writeConfig from '../agents/tools/write_config.js';
import { decideApproval, readApproval } from '../src/acs/approval.js';
import { digest } from '../src/acs/canonical.js';
import { ANNOTATION_KEY, acsAnnotation, groundedTool } from '../src/acs/grounded.js';
import { lintPromptTools } from '../src/acs/lint.js';
import { CAPABILITIES, effectiveFlags } from '../src/acs/ontology.js';
import { readCheckpoints, readTrace } from '../src/acs/records.js';
import { SETTINGS_PATH } from '../src/example/settings.js';
import annotationSchema from '../../../schemas/interop/standard_agents_annotation.schema.json' with { type: 'json' };
import manifest from '../package.json' with { type: 'json' };
import { memoryThread, user, type MemoryThread } from './memory_thread.js';

const CHANGE = { key: 'retries', value: '5' };

function thread(): MemoryThread {
  const t = memoryThread();
  t.files.set(SETTINGS_PATH, '{"retries":"3"}');
  return t;
}

function data(result: ToolResult): Record<string, unknown> {
  expect(result.status, result.error).toBe('success');
  return JSON.parse(result.result ?? 'null') as Record<string, unknown>;
}

/** The digest an approver decides on, as the refused call reported it. */
function digestOf(result: ToolResult): string {
  expect(result.error_code).toBe('F502');
  return result.error_data?.['digest'] as string;
}

async function post(t: MemoryThread, caller: ReturnType<typeof user> | null, body: unknown): Promise<Response> {
  const request = new Request('https://runtime.example/threads/thread-1/acs/approvals', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return approvalsPost(request, t.state, {}, { caller, threadAccess: caller !== null });
}

describe('classification', () => {
  it('annotates each tool with its capability and effective flags', () => {
    expect(acsAnnotation(writeConfig)).toEqual({
      standard: '1.1.0',
      ontology: '2.1.0',
      capability: 'mutate',
      layer: 'EXECUTE',
      domain: 'config',
      risk: 'high',
      mutation: true,
      requires_checkpoint: true,
      requires_approval: true,
    });
    expect(acsAnnotation(readConfig)).toMatchObject({ capability: 'retrieve', risk: 'low', mutation: false });
  });

  it("keeps other owners' annotation keys", () => {
    const tool = groundedTool({
      name: 'noop',
      capability: 'observe',
      description: 'Observe nothing.',
      args: z.object({}),
      annotations: { agentbuilder: { codemode: { language: 'typescript' } } },
      execute: async () => ({ observation: null, evidence_anchors: [], confidence: 1 }),
    });
    expect(Object.keys(tool.annotations ?? {})).toEqual(['agentbuilder', ANNOTATION_KEY]);
  });

  it('takes flags from the ontology, and lets a tool only raise them', () => {
    expect(effectiveFlags('mutate').flags).toMatchObject({ requires_checkpoint: true, requires_approval: true });
    expect(effectiveFlags('observe', { requires_approval: true }).flags.requires_approval).toBe(true);
    expect(effectiveFlags('mutate', { risk: 'low' })).toMatchObject({ flags: { risk: 'high' } });
    expect(effectiveFlags('mutate', { risk: 'low' }).warnings[0]).toMatch(/^W602/);
    expect(effectiveFlags('audit', { mutation: false }).flags.mutation).toBe(false);
    expect(effectiveFlags('persist', { mutation: false }).flags.mutation).toBe(true);
  });

  it('refuses to define a tool that declares weaker flags', () => {
    expect(() =>
      groundedTool({
        name: 'quiet_write',
        capability: 'mutate',
        flags: { risk: 'low' },
        description: 'x',
        args: z.object({}),
        execute: async () => ({ success: true, evidence_anchors: [] }),
      }),
    ).toThrow(/W602/);
  });
});

/** Ask for the change, and have `who` approve it. Returns the digest. */
async function approve(t: MemoryThread, args = CHANGE, who = 'alice'): Promise<string> {
  const d = digestOf(await writeConfig.execute(t.state, args));
  await decideApproval(t.state, user(who), d, 'approved', Date.now());
  return d;
}

describe('checkpoint before mutation', () => {
  it('refuses an approved mutation when no checkpoint has run, and keeps the approval', async () => {
    const t = thread();
    const d = await approve(t);

    const result = await writeConfig.execute(t.state, CHANGE);
    expect(result).toMatchObject({ status: 'error', error_code: 'F501' });
    expect(result.error_data).toMatchObject({
      code: 'F501',
      name: 'CHECKPOINT_REQUIRED',
      severity: 'error',
      location: { tool: 'write_config', capability: 'mutate' },
    });
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
    expect((await readApproval(t.state, d))?.used_at).toBeUndefined();

    // The restore point is taken after the approval, just before the change.
    await checkpointConfig.execute(t.state, { label: 'before change' });
    data(await writeConfig.execute(t.state, CHANGE));
    expect(JSON.parse(t.files.get(SETTINGS_PATH) ?? '')).toEqual({ retries: '5' });
  });

  it('does not accept a checkpoint taken before the thread last went idle', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'taken too early' });
    await approve(t);

    // The thread waited for the person; the approved call runs in a new execution.
    t.newExecution();
    const result = await writeConfig.execute(t.state, CHANGE);
    expect(result).toMatchObject({ status: 'error', error_code: 'F501' });
    expect(result.error).toMatch(/before this thread last went idle/);
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');

    await checkpointConfig.execute(t.state, { label: 'just before the change' });
    data(await writeConfig.execute(t.state, CHANGE));
    expect((await readTrace(t.state)).at(-1)).toMatchObject({ flow_id: 'flow-2', checkpoint_id: 'cp-4' });
  });

  it('refuses a rollback when no checkpoint has run', async () => {
    const t = thread();
    const result = await rollbackConfig.execute(t.state, { checkpoint_id: 'cp-1' });
    expect(result).toMatchObject({ status: 'error', error_code: 'F503' });
  });

  it('uses up one checkpoint per mutation', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'first change' });
    await approve(t);
    data(await writeConfig.execute(t.state, CHANGE));
    expect((await readCheckpoints(t.state)).map((c) => c.valid)).toEqual([false]);

    // A second change, approved, still needs a checkpoint of its own.
    const second = { key: 'retries', value: '9' };
    await approve(t, second);
    const result = await writeConfig.execute(t.state, second);
    expect(result).toMatchObject({ status: 'error', error_code: 'F501' });
    expect(JSON.parse(t.files.get(SETTINGS_PATH) ?? '')).toEqual({ retries: '5' });
  });
});

describe('approval bound to what was shown', () => {
  it('refuses until a person approves, and leaves the checkpoint valid', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'before change' });
    const result = await writeConfig.execute(t.state, CHANGE);

    expect(result).toMatchObject({ status: 'error', error_code: 'F502' });
    const shown = [{ action: 'write_config', capability: 'mutate', args: CHANGE }];
    expect(result.error_data).toMatchObject({ shown, state: 'pending', digest: await digest(shown) });
    expect((await readCheckpoints(t.state)).map((c) => c.valid)).toEqual([true]);
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
  });

  it('runs once approved, and an approval is single-use', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'one' });
    const refused = await writeConfig.execute(t.state, CHANGE);
    await decideApproval(t.state, user('alice'), digestOf(refused), 'approved', Date.now());

    const output = data(await writeConfig.execute(t.state, CHANGE));
    expect(output).toMatchObject({ success: true, previous_state: { retries: '3' }, new_state: { retries: '5' } });
    expect((await readApproval(t.state, digestOf(refused)))?.used_at).toBeTypeOf('number');

    // The same change again starts a new request: the old approval is spent.
    await checkpointConfig.execute(t.state, { label: 'two' });
    expect(await writeConfig.execute(t.state, CHANGE)).toMatchObject({ error_code: 'F502' });
  });

  it('does not let an approval for one change authorise another', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'one' });
    const refused = await writeConfig.execute(t.state, CHANGE);
    await decideApproval(t.state, user('alice'), digestOf(refused), 'approved', Date.now());

    const other = await writeConfig.execute(t.state, { key: 'retries', value: '500' });
    expect(other).toMatchObject({ status: 'error', error_code: 'F502' });
    expect(digestOf(other)).not.toBe(digestOf(refused));
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
  });

  it('stays refused after a rejection', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'one' });
    const refused = await writeConfig.execute(t.state, CHANGE);
    await decideApproval(t.state, user('alice'), digestOf(refused), 'rejected', Date.now());
    // A rejected request is closed; asking again opens a fresh round and
    // keeps the rejection on record.
    expect(await writeConfig.execute(t.state, CHANGE)).toMatchObject({
      error_code: 'F502',
      error_data: { state: 'pending' },
    });
    const record = await readApproval(t.state, digestOf(refused));
    expect(record?.decisions).toEqual([]);
    expect(record?.history).toEqual([
      expect.objectContaining({ decisions: [expect.objectContaining({ approver: 'alice', decision: 'rejected' })] }),
    ]);
  });

  it('counts distinct approvers, checks the role, and lets approvals expire', async () => {
    let clock = 1_000;
    const tool = groundedTool({
      name: 'release',
      capability: 'execute',
      description: 'Run the release.',
      approval: { min_approvers: 2, role: 'release-manager', expires_ms: 60_000 },
      args: z.object({ version: z.string() }),
      now: () => clock,
      execute: async () => ({ result: 'released', success: true, evidence_anchors: [] }),
    });
    const t = thread();
    const d = digestOf(await tool.execute(t.state, { version: '1.2.0' }));

    await expect(decideApproval(t.state, user('mallory'), d, 'approved', clock)).rejects.toThrow(/release-manager/);
    await decideApproval(t.state, user('alice', ['release-manager']), d, 'approved', clock);
    await expect(decideApproval(t.state, user('alice', ['release-manager']), d, 'approved', clock)).rejects.toThrow(
      /already decided/,
    );
    expect(await tool.execute(t.state, { version: '1.2.0' })).toMatchObject({ error_data: { state: 'pending' } });

    await decideApproval(t.state, user('bob', ['release-manager']), d, 'approved', clock);
    clock += 60_001;
    expect(await tool.execute(t.state, { version: '1.2.0' })).toMatchObject({ error_code: 'F502' });
  });
});

describe('the approval endpoint', () => {
  it('lists what is pending and records the authenticated caller', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'one' });
    const d = digestOf(await writeConfig.execute(t.state, CHANGE));

    const listed = (await (
      await approvalsGet(new Request('https://runtime.example/x'), t.state, {}, { caller: user('alice'), threadAccess: true })
    ).json()) as { approvals: { digest: string; shown: unknown }[] };
    expect(listed.approvals).toEqual([
      expect.objectContaining({ digest: d, shown: [{ action: 'write_config', capability: 'mutate', args: CHANGE }] }),
    ]);

    const response = await post(t, user('alice'), { digest: d, decision: 'approved' });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ digest: d, state: 'approved' });
    expect(t.queued).toEqual([expect.objectContaining({ role: 'user', silent: true })]);

    data(await writeConfig.execute(t.state, CHANGE));
    const entry = (await readTrace(t.state)).at(-1);
    expect(entry?.approval).toMatchObject({ digest: d, approvers: ['alice'] });
  });

  it('refuses an anonymous caller, a malformed body and an unknown request', async () => {
    const t = thread();
    expect((await post(t, null, { digest: 'a'.repeat(64), decision: 'approved' })).status).toBe(401);
    expect((await post(t, user('alice'), { decision: 'approved' })).status).toBe(400);
    expect((await post(t, user('alice'), { digest: 'a'.repeat(64), decision: 'approved' })).status).toBe(404);
  });
});

describe('evidence and audit trail', () => {
  it('rejects an output that lacks a field the ontology requires', async () => {
    const tool = groundedTool({
      name: 'ungrounded_read',
      capability: 'retrieve',
      description: 'x',
      args: z.object({}),
      // @ts-expect-error the retrieve output requires evidence_anchors and confidence
      execute: async () => ({ data: 1 }),
    });
    const t = thread();
    const result = await tool.execute(t.state, {});
    expect(result).toMatchObject({ status: 'error' });
    expect(result.error).toMatch(/missing evidence_anchors, confidence/);
    expect((await readTrace(t.state)).at(-1)).toMatchObject({ status: 'failed' });
  });

  it('records every call, including refusals, with its evidence', async () => {
    const t = thread();
    await readConfig.execute(t.state, {});
    await approve(t);
    await writeConfig.execute(t.state, CHANGE);
    const cp = data(await checkpointConfig.execute(t.state, { label: 'one' }));
    await writeConfig.execute(t.state, CHANGE);
    data(await verifyConfig.execute(t.state, { key: 'retries', expected: '5' }));

    const trace = await readTrace(t.state);
    expect(trace.map((e) => [e.seq, e.action, e.capability, e.status, e.code ?? null])).toEqual([
      [1, 'read_config', 'retrieve', 'executed', null],
      [2, 'write_config', 'mutate', 'refused', 'F502'],
      [3, 'write_config', 'mutate', 'refused', 'F501'],
      [4, 'checkpoint_config', 'checkpoint', 'executed', null],
      [5, 'write_config', 'mutate', 'executed', null],
      [6, 'verify_config', 'verify', 'executed', null],
    ]);
    expect(trace[4]).toMatchObject({ checkpoint_id: cp['checkpoint_id'], approval: { approvers: ['alice'] } });
    expect(trace[4]?.evidence_anchors).toHaveLength(2);
    expect(trace[0]?.args_digest).toBe(await digest({}));
  });

  it('restores the checkpointed document on rollback', async () => {
    const t = thread();
    const cp = data(await checkpointConfig.execute(t.state, { label: 'one' }));
    const refused = await writeConfig.execute(t.state, CHANGE);
    await decideApproval(t.state, user('alice'), digestOf(refused), 'approved', Date.now());
    await writeConfig.execute(t.state, CHANGE);

    const output = data(await rollbackConfig.execute(t.state, { checkpoint_id: cp['checkpoint_id'] as string }));
    expect(output).toMatchObject({ restored: true, restored_state: { retries: '3' } });
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
  });

  it('joins tool call ids to grounded entries and records ungrounded calls', async () => {
    const t = thread();
    const call = (id: string, name: string): HookToolCall => ({ id, type: 'function', function: { name, arguments: '{}' } });
    const context = { source: { kind: 'prompt', promptName: 'config_steward' } } as const;

    await readConfig.execute(t.state, {});
    await auditHook.execute(t.state, call('call_1', 'read_config'), { status: 'success' }, context);
    await auditHook.execute(t.state, call('call_2', 'web_search'), { status: 'error', error: 'offline' }, context);

    expect(await readTrace(t.state)).toEqual([
      expect.objectContaining({ seq: 1, action: 'read_config', capability: 'retrieve', tool_call_id: 'call_1' }),
      expect.objectContaining({ seq: 2, action: 'web_search', capability: null, status: 'failed', tool_call_id: 'call_2' }),
    ]);
  });
});

describe('the agent definition', () => {
  it('is a valid Standard Agent', () => {
    expect(validateAgentDefinition(configSteward)).toEqual([]);
  });

  it('offers a tool for everything its tools require', () => {
    const tools = {
      read_config: readConfig,
      checkpoint_config: checkpointConfig,
      write_config: writeConfig,
      verify_config: verifyConfig,
      rollback_config: rollbackConfig,
    };
    expect(lintPromptTools('config_steward', tools)).toEqual([]);

    // Without the checkpoint tool the write and the rollback could never run.
    const { checkpoint_config: _removed, ...withoutCheckpoint } = tools;
    expect(lintPromptTools('config_steward', withoutCheckpoint).map((d) => [d.code, d.location.tool])).toEqual([
      ['V102', 'write_config'],
      ['V102', 'rollback_config'],
    ]);

    // A tool defined with plain defineTool is reported as unclassified.
    const plain = { ...tools, web_search: { annotations: { agentbuilder: {} } } };
    expect(lintPromptTools('config_steward', plain)).toEqual([
      expect.objectContaining({ code: 'unclassified', severity: 'warning', location: { prompt: 'config_steward', tool: 'web_search' } }),
    ]);
  });

  it('offers only grounded tools, each with an annotation the schema accepts', () => {
    const tools = {
      read_config: readConfig,
      checkpoint_config: checkpointConfig,
      write_config: writeConfig,
      verify_config: verifyConfig,
      rollback_config: rollbackConfig,
    };
    expect(prompt.tools).toEqual(Object.keys(tools));
    const validate = new Ajv2020().compile(annotationSchema);
    for (const [name, tool] of Object.entries(tools)) {
      const annotation = acsAnnotation(tool);
      expect(validate(annotation), `${name}: ${JSON.stringify(validate.errors)}`).toBe(true);
      expect(Object.hasOwn(CAPABILITIES, annotation?.capability ?? '')).toBe(true);
    }
    expect(validate({ ...acsAnnotation(writeConfig), capability: 'detect-anomaly' })).toBe(false);
  });
});

describe('the package', () => {
  it('exports what Packaging describes, with every tool still classified', async () => {
    const pkg: PackedExports = await import('../src/package.js');

    expect(pkg.__meta.packageId).toBe(manifest.name);
    expect(pkg.__meta.entryAgents).toEqual(manifest.standardagent.entryAgents);
    expect(Object.keys(pkg.threadEndpoints ?? {})).toEqual(manifest.standardagent.threadEndpoints);
    expect(manifest.keywords).toContain('standardagent');

    for (const agentName of pkg.__meta.entryAgents) {
      const agent = await pkg.agents[agentName]?.();
      expect(validateAgentDefinition(agent)).toEqual([]);
    }

    // Everything a prompt names is in the package, and each tool is classified.
    for (const loadPrompt of Object.values(pkg.prompts)) {
      const packed = await loadPrompt();
      expect(Object.keys(pkg.models)).toContain(packed.model);
      for (const hook of packed.hooks ?? []) expect(Object.keys(pkg.hooks)).toContain(hook);
      for (const tool of packed.tools ?? []) {
        const name = typeof tool === 'string' ? tool : tool.name;
        const definition = await pkg.tools[name]?.();
        expect(definition, name).toBeDefined();
        expect(acsAnnotation(definition ?? {}), name).not.toBeNull();
      }
    }
  });
});
