/**
 * Evidence, grounding and secrets in the binding (STANDARD v1.2.0 §3.1,
 * §5.20, §6.5–§6.7): the anchors the example tools return, the `grounding`
 * and `seen` options, the default output check left as 1.1's, the persist
 * and audit secret refusals, redaction of every trace entry, the
 * `acs.evidence_recorded` notification and the thread's evidence export.
 */
import { Ajv2020 } from 'ajv/dist/2020.js';
import { refsIn, type Json } from '@synaptiai/acs-core';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import checkpointConfig from '../agents/tools/checkpoint_config.js';
import readConfig from '../agents/tools/read_config.js';
import {
  EVIDENCE_EVENT,
  EVIDENCE_STORE_INFO,
  exportEvidence,
  exportEvidenceJsonl,
  findEvidence,
  getEvidence,
} from '../src/acs/evidence.js';
import { groundedTool } from '../src/acs/grounded.js';
import { readTrace } from '../src/acs/records.js';
import { SETTINGS_PATH, fileAnchor, readSettings } from '../src/example/settings.js';
import evidenceSchema from '../../../schemas/interop/evidence.schema.json' with { type: 'json' };
import { memoryThread } from './memory_thread.js';

const args = z.object({}).passthrough();
const SCHEMA = evidenceSchema as { $defs: Record<string, unknown> };
const ajv = new Ajv2020({ strict: false });
const validator = (name: string) =>
  ajv.compile({ $defs: SCHEMA.$defs, $ref: `#/$defs/${name}` } as Record<string, unknown>);
const isRecorded = validator('EvidenceRecorded');
const isRecord = validator('EvidenceRecord');

describe('the example tools return evidence anchors (§6.5)', () => {
  it('fileAnchor carries a digest of kind file', () => {
    expect(fileAnchor('/a', 'ab'.repeat(32))).toEqual({ ref: 'file:/a', kind: 'file', digest: `sha256:${'ab'.repeat(32)}` });
  });

  it('checkpoint_config grounds its output in the record of the checkpoint', async () => {
    const t = memoryThread();
    t.files.set(SETTINGS_PATH, '{"retries": "3"}');
    const result = await checkpointConfig.execute(t.state, { label: 'before' });
    expect(result.status).toBe('success');
    const output = JSON.parse(result.result as string) as { checkpoint_id: string; evidence_anchors: Json[] };
    expect(output.evidence_anchors[0]).toEqual({ ref: `checkpoint:${output.checkpoint_id}`, kind: 'record' });
  });
});

describe('grounding policies (§5.20)', () => {
  const loose = { ref: 'file:x' };
  const make = (grounding?: { require: ['recall']; attested?: boolean }, output?: Record<string, Json>) =>
    groundedTool({
      name: 'recall_note',
      capability: 'recall',
      description: 'x',
      args,
      ...(grounding ? { grounding } : {}),
      execute: async () =>
        (output ?? {
          data: 'n',
          evidence_anchors: [loose],
          inference_method: 'llm-reasoning',
          confidence: 5,
        }) as never,
    });

  it('leaves the default output check as 1.1 had it', async () => {
    const t = memoryThread();
    // A kind-less anchor, a free inference_method and an optional
    // confidence outside 0..1: not checked without a policy.
    expect((await make().execute(t.state, {})).status).toBe('success');
  });

  it('refuses an ungrounded output under a policy, and records the entry failed', async () => {
    const t = memoryThread();
    const result = await make({ require: ['recall'] }).execute(t.state, {});
    expect(result.status).toBe('error');
    expect(result.error).toMatch(/^F505 PROVENANCE_MISSING:/);
    expect((await readTrace(t.state)).at(-1)).toMatchObject({ status: 'failed', code: 'F505' });
  });

  it('accepts a grounded or inferred output under a policy', async () => {
    const t = memoryThread();
    const grounded = make({ require: ['recall'] }, { data: 'n', evidence_anchors: [{ ref: 'file:x', kind: 'file' }] });
    expect((await grounded.execute(t.state, {})).status).toBe('success');
    const inferred = make(
      { require: ['recall'] },
      { data: 'n', evidence_anchors: [], inference_method: 'model_knowledge', confidence: 0.4 },
    );
    expect((await inferred.execute(t.state, {})).status).toBe('success');
  });

  it('refuses a policy with an unknown capability when the tool is defined', () => {
    expect(() => make({ require: ['clasify'] as never })).toThrow(/V101/);
  });

  it('attests only what this call received and read', async () => {
    const t = memoryThread();
    t.files.set(SETTINGS_PATH, '{"retries": "3"}');
    // An earlier call left the settings file in the trace.
    expect((await readConfig.execute(t.state, {})).status).toBe('success');
    const cites = (seen: (call: { args: Record<string, unknown> }) => string[]) =>
      groundedTool({
        name: 'read_settings',
        capability: 'retrieve',
        description: 'x',
        args,
        grounding: { require: ['retrieve'], attested: true },
        seen,
        execute: async (state) => {
          const { sha256 } = await readSettings(state);
          return { data: {}, evidence_anchors: [fileAnchor(SETTINGS_PATH, sha256)], confidence: 1 };
        },
      });
    // The stored trace is not a source: the arguments alone attest nothing.
    const argsOnly = await cites(({ args }) => refsIn(args as Json)).execute(t.state, {});
    expect(argsOnly.error).toMatch(/^F505/);
    // The file the tool's own code read is.
    const read = await cites(({ args }) => [...refsIn(args as Json), `file:${SETTINGS_PATH}`]).execute(t.state, {});
    expect(read.status).toBe('success');
  });
});

describe('secrets (§6.7)', () => {
  it('refuses persist data that holds a credential, and lets prose pass', async () => {
    const persist = groundedTool({
      name: 'remember',
      capability: 'persist',
      description: 'x',
      args: z.object({ note: z.string() }),
      execute: async () => ({ stored: true, evidence_anchors: [] }),
    });
    const t = memoryThread();
    const refused = await persist.execute(t.state, { note: 'aws key AKIAABCDEFGHIJKLMNOP' });
    expect(refused.error).toMatch(/^F504 CONSTRAINT_VIOLATED:/);
    const entry = (await readTrace(t.state)).at(-1);
    expect(entry).toMatchObject({ status: 'refused', code: 'F504' });
    expect(JSON.stringify(entry)).not.toContain('AKIAABCDEFGHIJKLMNOP');
    expect((await persist.execute(t.state, { note: 'token: rotate monthly' })).status).toBe('success');
  });

  it('refuses an audit record that holds a registered secret', async () => {
    const audit = groundedTool({
      name: 'log_event',
      capability: 'audit',
      description: 'x',
      args: z.object({ event: z.string() }),
      secrets: ['s3cr3t-value'],
      execute: async () => ({ recorded: true, evidence_anchors: [] }),
    });
    const t = memoryThread();
    expect((await audit.execute(t.state, { event: 'deployed with s3cr3t-value' })).error).toMatch(/^F504/);
  });

  it('redacts every trace entry, with no secrets option', async () => {
    const t = memoryThread();
    const leaky = groundedTool({
      name: 'fetch',
      capability: 'retrieve',
      description: 'x',
      args,
      execute: async () => ({
        data: 1,
        evidence_anchors: [{ ref: 'https://api.example.org/x?token=abcd1234', kind: 'url' }],
        confidence: 1,
      }),
    });
    expect((await leaky.execute(t.state, {})).status).toBe('success');
    const failing = groundedTool({
      name: 'fetch_more',
      capability: 'retrieve',
      description: 'x',
      args,
      execute: async () => {
        throw new Error('upstream said Authorization: Bearer abcdefghijklmnopqrstuv');
      },
    });
    expect((await failing.execute(t.state, {})).status).toBe('error');
    const stored = JSON.stringify(await readTrace(t.state));
    expect(stored).not.toContain('abcd1234');
    expect(stored).not.toContain('abcdefghijklmnopqrstuv');
    expect(stored).toContain('[REDACTED]');
    // The notification was redacted the same way.
    expect(JSON.stringify(t.emitted)).not.toContain('abcd1234');
  });

  it('never stores a registered value', async () => {
    const t = memoryThread();
    const tool = groundedTool({
      name: 'fetch',
      capability: 'retrieve',
      description: 'x',
      args,
      secrets: async () => ['s3cr3t-value'],
      execute: async () => ({ data: 1, evidence_anchors: [{ ref: 'file:s3cr3t-value', kind: 'file' }], confidence: 1 }),
    });
    expect((await tool.execute(t.state, {})).status).toBe('success');
    expect(JSON.stringify(await readTrace(t.state))).not.toContain('s3cr3t-value');
    expect(JSON.stringify(t.emitted)).not.toContain('s3cr3t-value');
  });

  it('keeps no digest of what an anchor that held a secret cites', async () => {
    // The digest of `DB_PASSWORD=sunshine42\n`, and of `sunshine42` alone:
    // with the redacted excerpt beside it, a guess of the password could be
    // checked against either (§6.7).
    const framed = 'sha256:58450d2be404c0431af23ddfe25cb85db350e5bff557e779024ecc6e629d1f3c';
    const alone = 'sha256:473fc524c94137859fe6927567786bd20e3cafed4c866efb5033963e18f8907d';
    const clean = 'sha256:fc54daf6865cec6354a8ada602faade2a408b3acbe4d2357274d21f7cd0cb9e1';
    const t = memoryThread();
    const tool = groundedTool({
      name: 'read_env',
      capability: 'retrieve',
      description: 'x',
      args,
      secrets: async () => ['hunter2-registered'],
      execute: async () => ({
        data: 1,
        evidence_anchors: [
          { ref: 'file:config/.env', kind: 'file', excerpt: 'DB_PASSWORD=sunshine42\n', digest: framed },
          { ref: 'file:secrets/db', kind: 'file', excerpt: 'hunter2-registered', digest: alone },
          { ref: 'file:report.txt', kind: 'file', excerpt: 'report body', digest: clean },
        ],
        confidence: 1,
      }),
    });
    expect((await tool.execute(t.state, {})).status).toBe('success');
    const anchors = (await readTrace(t.state)).at(-1)?.evidence_anchors;
    expect(anchors).toEqual([
      { ref: 'file:config/.env', kind: 'file', excerpt: 'DB_PASSWORD=[REDACTED]\n', metadata: { digest_omitted: 'secret' } },
      { ref: 'file:secrets/db', kind: 'file', excerpt: '[REDACTED]', metadata: { digest_omitted: 'secret' } },
      { ref: 'file:report.txt', kind: 'file', excerpt: 'report body', digest: clean },
    ]);
    for (const where of [JSON.stringify(await readTrace(t.state)), JSON.stringify(t.emitted)]) {
      expect(where).not.toContain(framed);
      expect(where).not.toContain(alone);
    }
    // The notification names the digest only of the anchor that kept one.
    expect(t.emitted.at(-1)?.data).toMatchObject({ anchors: [{ ref: 'file:config/.env' }, { ref: 'file:secrets/db' }, { digest: clean }] });
    const records = await exportEvidence(t.state);
    expect(records.every((r) => isRecord(r))).toBe(true);
  });
});

describe('the evidence notification and export (§6.6)', () => {
  it('emits one valid notification per call with anchors', async () => {
    const t = memoryThread();
    t.files.set(SETTINGS_PATH, '{"retries": "3"}');
    expect((await readConfig.execute(t.state, {})).status).toBe('success');
    expect(t.emitted).toHaveLength(1);
    const { event, data } = t.emitted[0]!;
    expect(event).toBe(EVIDENCE_EVENT);
    expect(isRecorded(data)).toBe(true);
    expect(data).toMatchObject({ type: 'acs.evidence_recorded', capability: 'retrieve', tool: 'read_config' });
  });

  it('a throwing emit does not fail the tool', async () => {
    const t = memoryThread();
    t.files.set(SETTINGS_PATH, '{"retries": "3"}');
    t.emitFails = new Error('socket closed');
    expect((await readConfig.execute(t.state, {})).status).toBe('success');
  });

  it('exports the thread as evidence records, a session store', async () => {
    const t = memoryThread();
    t.files.set(SETTINGS_PATH, '{"retries": "3"}');
    await readConfig.execute(t.state, {});
    const records = await exportEvidence(t.state);
    expect(records).toHaveLength(1);
    expect(records.every((r) => isRecord(r))).toBe(true);
    expect(records[0]).toMatchObject({ record_id: 'thread-1/1/0', run_id: 'flow-1', capability: 'retrieve', tool: 'read_config' });
    expect(EVIDENCE_STORE_INFO).toEqual({ durability: 'session', bounded: false });
  });

  it('returns a record by its id and filters by capability, kind and run, in append order', async () => {
    const t = memoryThread();
    t.files.set(SETTINGS_PATH, '{"retries": "3"}');
    await readConfig.execute(t.state, {});
    await checkpointConfig.execute(t.state, { label: 'before' });
    await readConfig.execute(t.state, {});
    const all = await exportEvidence(t.state);
    expect(all.length).toBeGreaterThanOrEqual(3);
    const first = all[0]!;
    expect(await getEvidence(t.state, first.record_id)).toEqual(first);
    expect(await getEvidence(t.state, 'thread-1/999/0')).toBeNull();
    const reads = await findEvidence(t.state, { capability: 'retrieve' });
    expect(reads.map((r) => r.record_id)).toEqual(all.filter((r) => r.capability === 'retrieve').map((r) => r.record_id));
    expect(reads).toHaveLength(2);
    const records = await findEvidence(t.state, { kind: 'record' });
    expect(records.length).toBeGreaterThan(0);
    expect(records.every((r) => r.anchor.kind === 'record' && r.capability === 'checkpoint')).toBe(true);
    expect(await findEvidence(t.state, { run_id: 'flow-1' })).toEqual(all);
    expect(await findEvidence(t.state, { run_id: 'other', capability: 'retrieve' })).toEqual([]);
    const lines = (await exportEvidenceJsonl(t.state)).split('\n');
    expect(lines.at(-1)).toBe('');
    expect(lines.slice(0, -1).map((l) => JSON.parse(l) as unknown)).toEqual(all);
  });
});
