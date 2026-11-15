// agents/api/acs/approvals.post.ts
import { defineThreadEndpoint } from '@standardagents/spec';
import { z } from 'zod';
import {
  ApprovalError,
  approvalRound,
  approvalState,
  decideApproval,
  readApproval,
} from '../../../src/acs/approval.js';
import type { ApprovalRecord } from '../../../src/acs/records.js';

// `round` is the round the person was shown (GET acs/approvals, or the F502
// refusal): a decision on a round that has closed since is refused, so it
// cannot approve the same values when they are asked for again.
const Decision = z.object({
  digest: z.string().regex(/^[0-9a-f]{64}$/),
  round: z.number().int().min(1),
  decision: z.enum(['approved', 'rejected']),
});

const STATUS: Record<ApprovalError['reason'], number> = {
  unknown_request: 404,
  not_authorized: 403,
  already_decided: 409,
  closed: 409,
};

// A person decides an approval request here. The runtime authenticates the
// request before this code runs, so `auth.caller` is who decided. A model can
// reach this only through a tool that holds a credential the runtime accepts,
// which a deployment must not give it.
export default defineThreadEndpoint(async (req, state, _params, auth) => {
  const caller = auth.caller;
  if (caller === null) {
    return Response.json({ error: 'An approval needs an authenticated caller' }, { status: 401 });
  }
  const body = Decision.safeParse(await req.json().catch(() => null));
  if (!body.success) {
    return Response.json({ error: 'Expected digest, round and decision' }, { status: 400 });
  }
  const { digest, round, decision } = body.data;

  const now = Date.now();
  let record: ApprovalRecord;
  try {
    record = await decideApproval(state, caller, digest, decision, now, round);
  } catch (error) {
    if (!(error instanceof ApprovalError)) throw error;
    // The same decision sent again, as a client does when it did not get the
    // answer, is answered as the first was, and the thread is woken again:
    // an approval while the round is still open, a rejection while it is the
    // rejection that closed the round.
    const repeated =
      error.reason === 'already_decided' || error.reason === 'closed' ? await readApproval(state, digest) : null;
    const standing = repeated === null ? null : approvalState(repeated, now);
    const same =
      repeated !== null &&
      approvalRound(repeated) === round &&
      repeated.decisions.some((d) => d.approver === caller.id && d.decision === decision) &&
      (decision === 'rejected' ? standing === 'rejected' : standing === 'pending' || standing === 'approved');
    if (!repeated || !same) {
      return Response.json({ error: error.message }, { status: STATUS[error.reason] });
    }
    record = repeated;
  }

  const standing = approvalState(record, now);
  let woken = true;
  if (standing !== 'pending') {
    // Wake the thread. The tool reads the record, never this message. The
    // decision is stored already, so a message that cannot be queued is
    // reported, not turned into an error the client would retry.
    try {
      await state.queueMessage({
        role: 'user',
        content: `Approval request ${record.digest.slice(0, 12)} is ${standing}.`,
        silent: true,
      });
    } catch {
      woken = false;
    }
  }
  return Response.json({ digest: record.digest, state: standing, ...(woken ? {} : { woken: false }) });
});
