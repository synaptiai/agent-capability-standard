// agents/api/acs/approvals.post.ts
import { defineThreadEndpoint } from '@standardagents/spec';
import { z } from 'zod';
import { ApprovalError, approvalState, decideApproval } from '../../../src/acs/approval.js';

const Decision = z.object({
  digest: z.string().regex(/^[0-9a-f]{64}$/),
  decision: z.enum(['approved', 'rejected']),
});

const STATUS: Record<ApprovalError['reason'], number> = {
  unknown_request: 404,
  not_authorized: 403,
  already_decided: 409,
  closed: 409,
};

// A person decides an approval request here. The runtime authenticates the
// request before this code runs, so `auth.caller` is who decided; the model
// has no way to call this.
export default defineThreadEndpoint(async (req, state, _params, auth) => {
  if (auth.caller === null) {
    return Response.json({ error: 'An approval needs an authenticated caller' }, { status: 401 });
  }
  const body = Decision.safeParse(await req.json().catch(() => null));
  if (!body.success) {
    return Response.json({ error: 'Expected digest and decision' }, { status: 400 });
  }

  const now = Date.now();
  try {
    const record = await decideApproval(state, auth.caller, body.data.digest, body.data.decision, now);
    const standing = approvalState(record, now);
    if (standing !== 'pending') {
      // Wake the thread. The tool reads the record, never this message.
      await state.queueMessage({
        role: 'user',
        content: `Approval request ${record.digest.slice(0, 12)} is ${standing}.`,
        silent: true,
      });
    }
    return Response.json({ digest: record.digest, state: standing });
  } catch (error) {
    if (error instanceof ApprovalError) {
      return Response.json({ error: error.message }, { status: STATUS[error.reason] });
    }
    throw error;
  }
});
