/**
 * A prerequisite other than a checkpoint that has not run is V102 (STANDARD
 * 1.2.0 §5.18.5, §9.1). Ontology 2.x has only `checkpoint` requires-edges,
 * so the binding's ontology is given an edge `observe -> generate` here.
 */
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { CODE_NAMES } from '../src/acs/records.js';
import { memoryThread } from './memory_thread.js';

vi.mock('../src/acs/ontology.js', async (original) => {
  const actual = await original<typeof import('../src/acs/ontology.js')>();
  return {
    ...actual,
    prerequisitesOf: (capabilities: readonly string[]) => [
      ...(capabilities.includes('generate') ? ['observe' as const] : []),
      ...actual.prerequisitesOf(capabilities as never),
    ],
  };
});

const { groundedTool } = await import('../src/acs/grounded.js');

const args = z.object({}).passthrough();
const look = groundedTool({
  name: 'look',
  capability: 'observe',
  description: 'look',
  args,
  execute: async () => ({ observation: 1, evidence_anchors: [], confidence: 1 }),
});
const draft = groundedTool({
  name: 'draft',
  capability: 'generate',
  description: 'draft',
  args,
  execute: async () => ({ content: 'x', evidence_anchors: [], confidence: 1 }),
});
const undo = groundedTool({
  name: 'undo',
  capability: 'rollback',
  description: 'undo',
  args,
  execute: async () => ({ restored: true, evidence_anchors: [] }),
});

describe('prerequisites other than a checkpoint', () => {
  it('refuses with V102 until the prerequisite ran, then runs', async () => {
    const t = memoryThread();
    const refused = await draft.execute(t.state, {});
    expect(refused).toMatchObject({ error_code: 'V102' });
    expect(refused.error).toMatch(new RegExp(`^V102 ${CODE_NAMES.V102}: `));
    expect((await look.execute(t.state, {})).status).toBe('success');
    expect((await draft.execute(t.state, {})).status).toBe('success');
  });

  it('keeps F503 for a rollback with no checkpoint', async () => {
    const t = memoryThread();
    expect((await undo.execute(t.state, {})).error_code).toBe('F503');
  });
});
