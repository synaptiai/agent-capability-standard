import { describe, expect, it } from 'vitest';
import { actionRecord, type TraceEntry } from '../src/acs/records.js';

const base: TraceEntry = {
  seq: 3,
  at: Date.UTC(2026, 10, 15, 12, 0, 0),
  action: 'apply_config',
  capability: 'mutate',
  status: 'executed',
};

/** No member is present with the value `undefined`. */
function defined(value: unknown): boolean {
  if (value === undefined) return false;
  if (Array.isArray(value)) return value.every(defined);
  if (value !== null && typeof value === 'object') return Object.values(value).every(defined);
  return true;
}

describe('actionRecord (STANDARD v1.2.0 §6.4)', () => {
  it('maps each status', () => {
    const statuses = {
      executed: 'executed',
      failed: 'failed',
      refused: 'rejected',
      started: 'approved',
    } as const;
    for (const [from, to] of Object.entries(statuses)) {
      const record = actionRecord({ ...base, status: from as TraceEntry['status'] }, 'thread-1');
      expect(record.status).toBe(to);
    }
  });

  it('gives a refused call its code', () => {
    const record = actionRecord({ ...base, status: 'refused', code: 'F501' }, 'thread-1');
    expect(record.status).toBe('rejected');
    expect(record.code).toBe('F501');
  });

  it('has the required members and correlation', () => {
    const record = actionRecord(
      {
        ...base,
        tool_call_id: 'call_1',
        checkpoint_id: 'cp1',
        args_digest: 'a'.repeat(64),
        flow_id: 'flow-1',
        step: 2,
        approval: { digest: 'b'.repeat(64), approvers: ['sa-user:1'], decision_ids: ['d1'] },
      },
      'thread-1',
    );
    expect(record).toMatchObject({
      action_id: 'thread-1/3',
      run_id: 'thread-1',
      timestamp: '2026-11-15T12:00:00.000Z',
      actor: 'agent',
      intent: 'apply_config call',
      tool: 'apply_config',
      capability: 'mutate',
      call_id: 'call_1',
      checkpoint_id: 'cp1',
      approval: { decision: 'approved', decision_id: 'd1', approvers: ['sa-user:1'] },
      details: { args_digest: 'a'.repeat(64), flow_id: 'flow-1', step: 2 },
      recorded_by: { name: 'standardagent-acs-binding' },
    });
  });

  it('leaves no member undefined, and omits a capability the call has none of', () => {
    const record = actionRecord({ ...base, capability: null }, 'thread-1');
    expect(defined(record)).toBe(true);
    expect('capability' in record).toBe(false);
    expect('details' in record).toBe(false);
    expect('approval' in record).toBe(false);
  });
});
