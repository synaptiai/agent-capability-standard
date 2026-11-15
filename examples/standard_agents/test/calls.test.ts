/**
 * The call-sequence fixtures (tests/conformance/calls/, STANDARD 1.2.0
 * §10.4) through `groundedTool` and `controlTool` tools built from each
 * fixture's bindings, over the memory thread.
 *
 * A boundary starts a new execution; an expired checkpoint moves the clock
 * past the ten-minute maximum age; an expired decision moves it past the
 * binding's `approval.expires`. Approvals are recorded before the call
 * (`requestApproval`, then `decideApproval` for each approver). A nested
 * call is made by the tool's own code with `state.invokeTool`. Fixtures
 * whose `needs` the binding's conformance statement lacks are skipped.
 */
import type { ThreadState, ToolResult } from '@standardagents/spec';
import { CAPABILITIES, type CapabilityId, parseDuration } from '@synaptiai/acs-core';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { ApprovalError, decideApproval, requestApproval, type ApprovalPolicy } from '../src/acs/approval.js';
import { controlTool, groundedTool } from '../src/acs/grounded.js';
import statement from '../../../tests/conformance/calls/statements/standard_agents_binding.json' with { type: 'json' };
import { memoryThread, user, type Invocable, type MemoryThread } from './memory_thread.js';

interface Binding {
  tool: string;
  capability?: CapabilityId;
  additional_capabilities?: CapabilityId[];
  invokes?: string[];
  approval?: { min_approvers?: number; role?: string; expires?: string };
  control?: true;
}

interface Call {
  call: string;
  args?: Record<string, unknown>;
  approve?: string[];
  reject?: string[];
  fails?: true;
  nested?: Call[];
  expect: 'run' | { refuse: string };
}

type Step = Call | { boundary: true } | { expire: 'checkpoint' | 'decision' };

interface Fixture {
  description: string;
  needs?: string[];
  bindings: Binding[];
  sequence: Step[];
}

const FIXTURES = import.meta.glob<Fixture>('../../../tests/conformance/calls/*.json', { eager: true, import: 'default' });
const CASES = Object.entries(FIXTURES).map(([path, f]) => [path.split('/').pop()!.replace('.json', ''), f] as const);
const FEATURES = new Set<string>(statement.features);
const TEN_MINUTES = 10 * 60 * 1000;

/** The output a capability's contract requires, with plain values. */
function outputOf(capability: CapabilityId, seq: number): Record<string, unknown> {
  const output: Record<string, unknown> = {};
  for (const field of CAPABILITIES[capability].output_required as readonly string[]) {
    output[field] = field === 'evidence_anchors' ? [] : field === 'confidence' ? 1 : field === 'checkpoint_id' ? `cp-${seq}` : true;
  }
  return output;
}

function policyOf(binding: Binding): ApprovalPolicy {
  const expires = binding.approval?.expires === undefined ? null : parseDuration(binding.approval.expires);
  return {
    ...(binding.approval?.min_approvers !== undefined ? { min_approvers: binding.approval.min_approvers } : {}),
    ...(binding.approval?.role !== undefined ? { role: binding.approval.role } : {}),
    ...(expires !== null ? { expires_ms: expires } : {}),
  };
}

class Runner {
  readonly t: MemoryThread = memoryThread();
  clock = Date.UTC(2026, 10, 15);
  readonly bindings = new Map<string, Binding>();
  /** What the current call of each tool does: fail, or make nested calls. */
  readonly scripts = new Map<string, Call>();
  readonly nestedOutcomes = new Map<Call, string>();

  constructor(bindings: Binding[]) {
    for (const b of bindings) this.bindings.set(b.tool, b);
    const built = new Map<string, Invocable>();
    const build = (name: string): Invocable => {
      const existing = built.get(name);
      if (existing) return existing;
      const b = this.bindings.get(name)!;
      let tool: Invocable;
      if (b.control) {
        tool = controlTool({ name, description: name, args: z.object({}).passthrough(), now: () => this.clock });
      } else {
        const invokes = Object.fromEntries((b.invokes ?? []).map((n) => [n, build(n)]));
        tool = groundedTool({
          name,
          capability: b.capability!,
          ...(b.additional_capabilities ? { additional_capabilities: b.additional_capabilities } : {}),
          ...(b.invokes ? { invokes: invokes as never } : {}),
          approval: policyOf(b),
          description: name,
          args: z.object({}).passthrough(),
          now: () => this.clock,
          execute: async (state: ThreadState, _args, call) => {
            const script = this.scripts.get(name);
            for (const nested of script?.nested ?? []) {
              this.nestedOutcomes.set(nested, outcome(await state.invokeTool(nested.call, nested.args ?? {})));
            }
            if (script?.fails) throw new Error(`${name} failed`);
            return outputOf(b.capability!, call.seq) as never;
          },
        });
      }
      built.set(name, tool);
      this.t.tools.set(name, tool);
      return tool;
    };
    for (const b of bindings) build(b.tool);
  }

  async decide(step: Call): Promise<void> {
    const binding = this.bindings.get(step.call)!;
    if (!step.approve && !step.reject) return;
    const shown = [{ action: step.call, capability: binding.capability!, args: (step.args ?? {}) as never }];
    const request = await requestApproval(this.t.state, shown, policyOf(binding), this.clock);
    for (const [who, decision] of [
      ...(step.approve ?? []).map((w) => [w, 'approved'] as const),
      ...(step.reject ?? []).map((w) => [w, 'rejected'] as const),
    ]) {
      try {
        await decideApproval(this.t.state, user(who), request.digest, decision, this.clock);
      } catch (error) {
        if (!(error instanceof ApprovalError && error.reason === 'already_decided')) throw error;
      }
    }
  }

  async call(step: Call): Promise<string> {
    await this.decide(step);
    this.scripts.set(step.call, step);
    const tool = this.t.tools.get(step.call)!;
    return outcome(await tool.execute(this.t.state, step.args ?? {}));
  }
}

/** A refusal's code, or `run` for a call that started (whether it then succeeded or failed). */
function outcome(result: ToolResult): string {
  return result.error_code ?? 'run';
}

describe('call-sequence fixtures', () => {
  it('reads all of them', () => {
    expect(CASES).toHaveLength(20);
  });

  it.for(CASES)('%s', async ([_name, fixture], { skip }) => {
    const missing = (fixture.needs ?? []).filter((n) => !FEATURES.has(n));
    // The binding sees no call of a tool it did not define (its statement).
    skip(missing.length > 0, `the binding's conformance statement lacks ${missing.join(', ')}`);
    const runner = new Runner(fixture.bindings);
    for (const [index, step] of fixture.sequence.entries()) {
      if ('boundary' in step) {
        runner.t.newExecution();
        continue;
      }
      if ('expire' in step) {
        if (step.expire === 'checkpoint') runner.clock += TEN_MINUTES + 1;
        else {
          const write = [...runner.bindings.values()].find((b) => b.approval?.expires !== undefined)!;
          runner.clock += (parseDuration(write.approval!.expires) ?? 0) + 1;
        }
        continue;
      }
      const expected = step.expect === 'run' ? 'run' : step.expect.refuse;
      expect(await runner.call(step), `step ${index} (${step.call})`).toBe(expected);
      for (const nested of step.nested ?? []) {
        const want = nested.expect === 'run' ? 'run' : nested.expect.refuse;
        expect(runner.nestedOutcomes.get(nested), `step ${index}, nested ${nested.call}`).toBe(want);
      }
    }
  });
});
