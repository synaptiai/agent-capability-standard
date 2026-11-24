/**
 * The call-sequence fixtures (tests/conformance/calls/, STANDARD 1.2.0
 * §10.4) through `groundedTool` and `controlTool` tools built from each
 * fixture's bindings, over the memory thread.
 *
 * A boundary starts a new execution; an expired checkpoint moves the clock
 * past the ten-minute maximum age; an expired decision moves it past the
 * binding's `approval.expires`. Approvals are recorded before the call
 * (`requestApproval`, then `decideApproval` for each approver). A nested
 * call is made by the tool's own code with `state.invokeTool`, and each
 * tool is registered (`registerTools`) under the name the memory thread
 * runs it under. A tool
 * returns what its output contract requires, or what the call `returns`,
 * which the binding checks (§5.18.10). Fixtures whose `needs` the binding's
 * conformance statement lacks are skipped.
 */
import type { ThreadState, ToolResult } from '@standardagents/spec';
import { CAPABILITIES, type CapabilityId, NotCanonicalizableError, parseDuration, parseJsonExact } from '@synaptiai/acs-core';
import { afterEach, describe, expect, it } from 'vitest';
import { z } from 'zod';
import { Ajv2020 } from 'ajv/dist/2020.js';
import {
  ApprovalError,
  MAX_APPROVERS,
  decideApproval,
  policyProblems,
  requestApproval,
  type ApprovalPolicy,
} from '../src/acs/approval.js';
import { CHECKPOINT_MAX_AGE_MS, LAYER_NAME, controlTool, groundedTool } from '../src/acs/grounded.js';
import { configureLayer, registerTools, resetLayer } from '../src/acs/layer.js';
import { ONTOLOGY_VERSION, STANDARD_VERSION } from '../src/acs/ontology.js';
import statement from '../../../tests/conformance/calls/statements/standard_agents_binding.json' with { type: 'json' };
import statementSchema from '../../../tests/conformance/calls/schema/statement.schema.json' with { type: 'json' };
import { memoryThread, user, type Invocable, type MemoryThread } from './memory_thread.js';

interface Binding {
  tool: string;
  capability?: CapabilityId;
  additional_capabilities?: CapabilityId[];
  invokes?: string[];
  approval?: { min_approvers?: number; role?: string; expires?: string };
  control?: true;
  destination?: string;
}

interface Call {
  call: string;
  args?: Record<string, unknown>;
  approve?: string[];
  reject?: string[];
  fails?: true;
  returns?: unknown;
  nested?: Call[];
  expect: 'run' | { refuse: string } | { refuse_output: string };
}

type Step = Call | { boundary: true } | { expire: 'checkpoint' | 'decision' };

interface Fixture {
  description: string;
  needs?: string[];
  without?: string[];
  destination_policy?: string[];
  bindings: Binding[];
  sequence: Step[];
}

// Read as text and parsed exactly, so that an argument beyond 2^53 reaches
// the tool as the fixture states it, not rounded by JSON.parse.
const FIXTURES = import.meta.glob<string>('../../../tests/conformance/calls/*.json', {
  eager: true,
  query: '?raw',
  import: 'default',
});
const CASES = Object.entries(FIXTURES).map(
  ([path, text]) => [path.split('/').pop()!.replace('.json', ''), parseJsonExact(text) as Fixture] as const,
);
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
          // The record's pointer, as the binding states it in the annotation.
          ...(b.destination !== undefined ? { destination: b.destination } : {}),
          approval: policyOf(b),
          description: name,
          args: z.object({}).passthrough(),
          now: () => this.clock,
          execute: async (state: ThreadState, _args, call) => {
            const script = this.scripts.get(name);
            for (const nested of script?.nested ?? []) {
              // A nested call runs under its own step: its `returns`,
              // `fails` and `nested`, not those of an earlier call.
              const result = await this.scripted(nested, () => state.invokeTool(nested.call, nested.args ?? {}));
              this.nestedOutcomes.set(nested, outcome(result));
            }
            if (script?.fails) throw new Error(`${name} failed`);
            if (script !== undefined && 'returns' in script) return script.returns as never;
            return outputOf(b.capability!, call.seq) as never;
          },
        });
      }
      built.set(name, tool);
      this.t.tools.set(name, tool);
      // The runner is the host: it registers each tool it runs under the
      // name, as a deployment registers the agent's tools (§5.18.4).
      registerTools({ [name]: tool });
      return tool;
    };
    for (const b of bindings) build(b.tool);
  }

  async decide(step: Call): Promise<void> {
    const binding = this.bindings.get(step.call)!;
    if (!step.approve && !step.reject) return;
    const shown = [{ action: step.call, capability: binding.capability!, args: (step.args ?? {}) as never }];
    let request: Awaited<ReturnType<typeof requestApproval>>;
    try {
      request = await requestApproval(this.t.state, shown, policyOf(binding), this.clock);
    } catch (error) {
      // Arguments with no canonical JSON (an integer literal beyond 2^53,
      // which parseJsonExact reads as a bigint): no decision can bind to
      // them (§5.18.7), so none is recorded, and the call meets F502.
      if (error instanceof NotCanonicalizableError) return;
      throw error;
    }
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

  /** Run `body` with `step` as what the current call of its tool does. */
  async scripted<T>(step: Call, body: () => Promise<T>): Promise<T> {
    const earlier = this.scripts.get(step.call);
    this.scripts.set(step.call, step);
    try {
      return await body();
    } finally {
      if (earlier === undefined) this.scripts.delete(step.call);
      else this.scripts.set(step.call, earlier);
    }
  }

  async call(step: Call): Promise<string> {
    await this.decide(step);
    const tool = this.t.tools.get(step.call)!;
    return outcome(await this.scripted(step, () => tool.execute(this.t.state, step.args ?? {})));
  }
}

/** A refusal's code, or `run` for a call that started (whether it then succeeded or failed). */
function outcome(result: ToolResult): string {
  return result.error_code ?? 'run';
}

/**
 * The outcome a step expects. A refused output's call ran; its code is what
 * the call returns, and the fixture's later steps show that it ran.
 */
function expected(step: Call): string {
  const want = step.expect;
  return want === 'run' ? 'run' : 'refuse' in want ? want.refuse : want.refuse_output;
}

describe("the binding's conformance statement", () => {
  it('follows the statement schema', () => {
    const validate = new Ajv2020({ strict: false }).compile(statementSchema);
    expect(validate(statement), JSON.stringify(validate.errors)).toBe(true);
  });

  it('states what the binding does', () => {
    expect(statement.layer).toEqual({ name: LAYER_NAME, version: STANDARD_VERSION });
    expect(statement.standard).toBe(STANDARD_VERSION);
    expect(statement.ontology).toBe(ONTOLOGY_VERSION);
    expect(parseDuration(statement.checkpoint_max_age)).toBe(CHECKPOINT_MAX_AGE_MS);
    // A policy without expires_ms sets no expiry.
    expect(statement.approval.expires).toBeNull();
    expect(statement.approval.how).toBe('recorded');
    expect(statement.approval.roles).toBe(true);
    expect(statement.approval.max_approvers).toBe(MAX_APPROVERS);
    expect(policyProblems({ min_approvers: MAX_APPROVERS })).toEqual([]);
    expect(policyProblems({ min_approvers: MAX_APPROVERS + 1 })).toHaveLength(1);
    // Every check of §5.18.10 is applied (class SL).
    expect('not_applied' in statement).toBe(false);
  });
});

describe('call-sequence fixtures', () => {
  it('reads all of them', () => {
    expect(CASES).toHaveLength(33);
  });

  afterEach(() => resetLayer());

  it.for(CASES)('%s', async ([_name, fixture], { skip }) => {
    const missing = (fixture.needs ?? []).filter((n) => !FEATURES.has(n));
    // The binding sees no call of a tool it did not define (its statement).
    skip(missing.length > 0, `the binding's conformance statement lacks ${missing.join(', ')}`);
    const present = (fixture.without ?? []).filter((n) => FEATURES.has(n));
    skip(present.length > 0, `the fixture is for a layer without ${present.join(', ')}`);
    if (fixture.destination_policy !== undefined) configureLayer({ destinations: [fixture.destination_policy] });
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
      expect(await runner.call(step), `step ${index} (${step.call})`).toBe(expected(step));
      for (const nested of step.nested ?? []) {
        expect(runner.nestedOutcomes.get(nested), `step ${index}, nested ${nested.call}`).toBe(expected(nested));
      }
    }
  });
});
