// agents/api/acs/approvals.get.ts
import { defineThreadEndpoint } from '@standardagents/spec';
import { approvalRound, listPendingApprovals } from '../../../src/acs/approval.js';

// What is waiting for a decision on this thread, with exactly what each
// approval would cover and the round a decision applies to. `authenticated`
// is the default access level.
export default defineThreadEndpoint(async (_req, state) => {
  const pending = await listPendingApprovals(state, Date.now());
  return Response.json({
    approvals: pending.map((record) => ({
      digest: record.digest,
      round: approvalRound(record),
      shown: record.shown,
      min_approvers: record.min_approvers,
      role: record.role ?? null,
      requested_at: record.requested_at,
      approved_by: record.decisions.map((d) => d.approver),
    })),
  });
});
