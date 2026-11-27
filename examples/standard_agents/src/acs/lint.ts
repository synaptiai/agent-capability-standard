/**
 * Definition-time checks of the tools a prompt offers and an agent binds
 * (STANDARD 1.2.0 §5.18.2).
 *
 * The workflow validator checks a workflow's steps against the ontology
 * before anything runs. A prompt has no steps, but it does have a fixed list
 * of tools, and each tool's `ai.synapti/acs` annotation is a carrier of its tool binding
 * record (§5.18.1). From that list alone a host can check that every tool is
 * bound (W617), that each binding names the tool it is offered under (V111),
 * and that no tool needs a capability the prompt can never perform (V102).
 * An agent definition adds a fourth: no stop or session action is tied to a
 * tool that can be refused (F506). The checks are the package's
 * `checkBindings`, which the Python loader mirrors.
 */
import type { AgentDefinition } from '@standardagents/spec';
import { agentsApply, annotationRecord, checkBindings, joinFlags, type BindingDiagnostic } from '@synaptiai/acs-core';
import { ANNOTATION_KEY, computedFlags, statedName } from './grounded.js';
import type { CapabilityId, SafetyFlags } from './ontology.js';

/** The prompt-side options that act when a named tool is called. */
export type ToolBinding = 'stopTool' | 'sessionStop' | 'sessionFail' | 'sessionStatus';

export interface LintDiagnostic {
  /**
   * W617 (UNBOUND_TOOL): a tool with no binding, whose calls are the
   * strictest case. V111 (TOOL_NAME_MISMATCH): a tool whose stated name is
   * not the name the prompt offers it under. V102 (MISSING_PREREQUISITE): a
   * tool that requires a capability no offered tool performs. F506
   * (GATED_CONTROL_ACTION): a stop or session action tied to a tool that can
   * be refused. V107 (UNRESOLVED_TARGET): an agent a workflow's `agents`
   * lists that the parent agent has no relationship to (§5.15.2).
   */
  code: 'V102' | 'W617' | 'V111' | 'F506' | 'V107';
  name: string;
  severity: 'error' | 'warning';
  message: string;
  location:
    | { prompt: string; tool: string; capability?: CapabilityId; prerequisite?: CapabilityId }
    | { agent: string; side: 'sideA' | 'sideB'; binding: ToolBinding; tool: string; capability?: CapabilityId }
    | { workflow: string; field: string; path: string; tool?: undefined };
}

type Tools = Record<string, { annotations?: Record<string, unknown> }>;

/**
 * The binding records the offered tools carry, what each offered name
 * carries (the record of the name the tool states, its `tool`, or null for
 * a tool with no `ai.synapti/acs` annotation), and, by that name, the effective flags
 * each tool defined here computed (`computedFlags`): the record states none
 * of those the applied domain profiles raise (§5.21.3), its own and the
 * layer's, and they are what its calls are checked with.
 */
function recordsOf(tools: Tools): {
  records: Record<string, unknown>[];
  offered: Record<string, string | null>;
  raised: Record<string, SafetyFlags>;
} {
  const records: Record<string, unknown>[] = [];
  const offered: Record<string, string | null> = {};
  const raised: Record<string, SafetyFlags> = {};
  const seen = new Set<string>();
  for (const [name, tool] of Object.entries(tools)) {
    const annotation = tool.annotations?.[ANNOTATION_KEY];
    const stated =
      (typeof annotation === 'object' && annotation !== null && typeof (annotation as { tool?: unknown }).tool === 'string'
        ? (annotation as { tool: string }).tool
        : undefined) ??
      statedName(tool) ??
      name;
    const record = annotationRecord(stated, annotation);
    if (!record) {
      offered[name] = null;
      continue;
    }
    offered[name] = stated;
    const computed = computedFlags(tool);
    if (computed !== undefined) raised[stated] = Object.hasOwn(raised, stated) ? joinFlags(raised[stated]!, computed) : computed;
    if (!seen.has(stated)) {
      seen.add(stated);
      records.push(record);
    }
  }
  return { records, offered, raised };
}

function capabilityOf(tools: Tools, name: string): CapabilityId | undefined {
  const annotation = tools[name]?.annotations?.[ANNOTATION_KEY] as { capability?: unknown } | undefined;
  return typeof annotation?.capability === 'string' ? (annotation.capability as CapabilityId) : undefined;
}

/**
 * Check the tools of one prompt (§5.18.2).
 *
 * - A tool with no `ai.synapti/acs` annotation is W617 (warning): its calls are
 *   treated as the strictest case.
 * - A tool whose stated name is not the name the prompt offers it under is
 *   V111 (error): an approver would be shown, and the trace would record,
 *   another tool's name.
 * - A tool whose capability `requires` another, or needs a checkpoint, when
 *   the prompt offers no tool of that capability, is V102 (error): the model
 *   could never get the call accepted. A host that takes checkpoints itself
 *   (`hostTakesCheckpoints`), or an offered tool whose binding names a
 *   `classifier`, counts as performing it. A shell-like tool performs only
 *   its worst case where no operating-system boundary is declared for it
 *   (§5.18.2); the binding covers none, and this lint cannot tell one.
 *
 * A tool defined here is checked with the flags it computed, those its
 * domain profiles and the layer's raise included (§5.21.3), which its
 * record does not state: they are what its calls are checked with.
 */
export function lintPromptTools(
  prompt: string,
  tools: Tools,
  options: { hostTakesCheckpoints?: boolean } = {},
): LintDiagnostic[] {
  const { records, offered, raised } = recordsOf(tools);
  const { diagnostics } = checkBindings(records, {
    offered,
    raised,
    hostActions: [],
    hostTakesCheckpoints: options.hostTakesCheckpoints ?? false,
  });
  return diagnostics
    .filter((d): d is BindingDiagnostic & { code: 'V102' | 'W617' | 'V111' } => ['V102', 'W617', 'V111'].includes(d.code))
    .map((d) => {
      const capability = capabilityOf(tools, d.location.tool);
      return {
        code: d.code,
        name: d.name,
        severity: d.severity,
        message: d.message,
        location: {
          prompt,
          tool: d.location.tool,
          ...(capability !== undefined && d.code !== 'W617' ? { capability } : {}),
          ...(d.location.prerequisite !== undefined ? { prerequisite: d.location.prerequisite as CapabilityId } : {}),
        },
      };
    });
}

/**
 * Check the tools an agent's prompt sides bind to a stop or session action
 * (§5.18.3, F506).
 *
 * `stopTool`, `sessionStop`, `sessionFail` and `sessionStatus` act when the
 * named tool is called. The Standard Agent Specification does not make any
 * of them depend on the call's result, so a grounded tool that is refused
 * could still end the turn or the session, and with `messageProperty` hand a
 * parent the model's text for an action that never ran. Tying one to a tool
 * that is unbound, has a prerequisite, or needs a checkpoint or approval is
 * F506: for a tool defined here, by the flags it computed, those the applied
 * domain profiles raise included (§5.21.3), as its calls are refused. Bind a
 * `controlTool`, which is never refused, that the model calls once the gated
 * one has succeeded.
 */
export function lintAgentBindings(
  agent: Pick<AgentDefinition, 'name' | 'sideA' | 'sideB'>,
  tools: Tools,
): LintDiagnostic[] {
  const out: LintDiagnostic[] = [];
  const { records, offered, raised } = recordsOf(tools);
  for (const side of ['sideA', 'sideB'] as const) {
    const config = agent[side];
    if (config.prompt === undefined) continue;
    const bound: [ToolBinding, string | undefined][] = [
      ['stopTool', config.stopTool],
      ['sessionStop', config.sessionStop?.name],
      ['sessionFail', config.sessionFail?.name],
      ['sessionStatus', config.sessionStatus?.name],
    ];
    const hostActions = bound
      .filter((b): b is [ToolBinding, string] => b[1] !== undefined)
      .map(([action, tool]) => ({ action, tool }));
    if (hostActions.length === 0) continue;
    const named: Record<string, string | null> = { ...offered };
    for (const { tool } of hostActions) if (!Object.hasOwn(named, tool)) named[tool] = null;
    const { diagnostics } = checkBindings(records, { offered: named, hostActions, raised });
    for (const d of diagnostics) {
      if (d.code !== 'F506') continue;
      const binding = d.location.action as ToolBinding;
      const capability = capabilityOf(tools, d.location.tool);
      out.push({
        code: 'F506',
        name: d.name,
        severity: 'error',
        message: `agent '${agent.name}' ties ${binding} to '${d.location.tool}'${capability ? ` (${capability})` : ''}: ${d.message}`,
        location: {
          agent: agent.name,
          side,
          binding,
          tool: d.location.tool,
          ...(capability !== undefined ? { capability } : {}),
        },
      });
    }
  }
  return out;
}

/** One RFC 6901 reference token. */
function pointerToken(token: string): string {
  return token.replace(/~/g, '~0').replace(/\//g, '~1');
}

/**
 * Check a workflow's declared agents against the relationships of the
 * agent that runs it (STANDARD 1.2.0 §5.15.2): Standard Agents composes
 * agents statically, so each agent the workflow's `agents` lists must be a
 * subagent the parent has a relationship to. A listed agent with none is
 * V107 at `agents[i]`, with its `path` (§9.8). `header` is the catalog
 * file's version header (`null` for none, §11.5): in a workflow that
 * targets 1.0 or 1.1, or declares no version, `agents` has no effect and
 * nothing is checked.
 */
export function lintDelegationTargets(
  workflowName: string,
  workflow: Record<string, unknown>,
  header: string | null,
  relationships: Iterable<string>,
): LintDiagnostic[] {
  if (!agentsApply(workflow, header)) return [];
  const listed = workflow['agents'];
  if (!Array.isArray(listed)) return [];
  const known = new Set(relationships);
  const out: LintDiagnostic[] = [];
  listed.forEach((agent, i) => {
    if (typeof agent !== 'string' || known.has(agent)) return;
    out.push({
      code: 'V107',
      name: 'UNRESOLVED_TARGET',
      severity: 'error',
      message: `the workflow lists agent '${agent}', but the agent that runs it has no relationship to it`,
      location: { workflow: workflowName, field: `agents[${i}]`, path: `/${pointerToken(workflowName)}/agents/${i}` },
    });
  });
  return out;
}
