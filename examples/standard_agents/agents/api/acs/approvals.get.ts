// agents/api/acs/approvals.get.ts
import { defineThreadEndpoint } from '@standardagents/spec';
import { listPendingApprovals } from '../../../src/acs/approval.js';

// What is waiting for a decision on this thread, with exactly what each
// approval would cover. `authenticated` is the default access level.
export default defineThreadEndpoint(async (_req, state) => {
  const pending = await listPendingApprovals(state, Date.now());
  return Response.json({
    approvals: pending.map(({ digest, shown, min_approvers, role, requested_at, decisions }) => ({
      digest,
      shown,
      min_approvers,
      role: role ?? null,
      requested_at,
      approved_by: decisions.map((d) => d.approver),
    })),
  });
});
