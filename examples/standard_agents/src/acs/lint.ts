/**
 * Definition-time checks of the tools a prompt offers and an agent binds.
 *
 * The workflow validator checks a workflow's steps against the ontology
 * before anything runs. A prompt has no steps, but it does have a fixed list
 * of tools, and two things can be checked from that list alone: every tool is
 * classified, and no tool needs a capability the prompt can never perform.
 * An agent definition adds a third: no tool that can be refused is bound to
 * a stop or session action.
 */
import type { AgentDefinition } from '@standardagents/spec';
import { acsAnnotation } from './grounded.js';
import { prerequisites, type CapabilityId } from './ontology.js';

/** The prompt-side options that act when a named tool is called. */
export type ToolBinding = 'stopTool' | 'sessionStop' | 'sessionFail' | 'sessionStatus';

export interface LintDiagnostic {
  /**
   * V102 (MISSING_PREREQUISITE, STANDARD v1.1.0 §9.2): a `requires` edge
   * that cannot be met. `unclassified` and `bound_gated_tool` are this
   * binding's own: the Standard has no code for a tool outside the ontology,
   * or for a host that acts on a call whatever its result.
   */
  code: 'V102' | 'unclassified' | 'bound_gated_tool';
  severity: 'error' | 'warning';
  message: string;
  location:
    | { prompt: string; tool: string; capability?: CapabilityId }
    | { agent: string; side: 'sideA' | 'sideB'; binding: ToolBinding; tool: string; capability: CapabilityId };
}

/**
 * Check the tools of one prompt.
 *
 * - A tool with no `acs` annotation is reported (`unclassified`, warning): its calls
 *   are not classified, so no rule applies to them.
 * - A tool whose capability `requires` another, or needs a checkpoint, when
 *   the prompt offers no tool of that capability, is an error (V102): the
 *   model could never get the call accepted.
 */
export function lintPromptTools(
  prompt: string,
  tools: Record<string, { annotations?: Record<string, unknown> }>,
): LintDiagnostic[] {
  const diagnostics: LintDiagnostic[] = [];
  const offered = new Set<CapabilityId>();
  for (const tool of Object.values(tools)) {
    const annotation = acsAnnotation(tool);
    if (annotation) offered.add(annotation.capability);
  }

  for (const [name, tool] of Object.entries(tools)) {
    const annotation = acsAnnotation(tool);
    if (!annotation) {
      diagnostics.push({
        code: 'unclassified',
        severity: 'warning',
        message: `tool '${name}' has no capability classification, so no safety rule applies to its calls`,
        location: { prompt, tool: name },
      });
      continue;
    }
    const needed = new Set<CapabilityId>(prerequisites(annotation.capability));
    if (annotation.requires_checkpoint) needed.add('checkpoint');
    for (const capability of needed) {
      if (!offered.has(capability)) {
        diagnostics.push({
          code: 'V102',
          severity: 'error',
          message: `tool '${name}' (${annotation.capability}) requires '${capability}', and the prompt offers no '${capability}' tool`,
          location: { prompt, tool: name, capability: annotation.capability },
        });
      }
    }
  }
  return diagnostics;
}

/**
 * Check the tools an agent's prompt sides bind to a stop or session action.
 *
 * `stopTool`, `sessionStop`, `sessionFail` and `sessionStatus` act when the
 * named tool is called. The Standard Agent Specification does not make any
 * of them depend on the call's result, so a grounded tool that is refused
 * could still end the turn or the session, and with `messageProperty` hand a
 * parent the model's text for an action that never ran. A tool that can be
 * refused (it needs approval, a checkpoint or a prerequisite) is therefore
 * an error when bound (`bound_gated_tool`). Bind a separate, ungated tool
 * that the model calls once the gated one has succeeded.
 */
export function lintAgentBindings(
  agent: Pick<AgentDefinition, 'name' | 'sideA' | 'sideB'>,
  tools: Record<string, { annotations?: Record<string, unknown> }>,
): LintDiagnostic[] {
  const diagnostics: LintDiagnostic[] = [];
  for (const side of ['sideA', 'sideB'] as const) {
    const config = agent[side];
    if (config.prompt === undefined) continue;
    const bound: [ToolBinding, string | undefined][] = [
      ['stopTool', config.stopTool],
      ['sessionStop', config.sessionStop?.name],
      ['sessionFail', config.sessionFail?.name],
      ['sessionStatus', config.sessionStatus?.name],
    ];
    for (const [binding, name] of bound) {
      const tool = name === undefined ? undefined : tools[name];
      const annotation = tool ? acsAnnotation(tool) : null;
      if (name === undefined || !annotation) continue;
      const needed = new Set<CapabilityId>(prerequisites(annotation.capability));
      if (annotation.requires_checkpoint) needed.add('checkpoint');
      const needs = [...(annotation.requires_approval ? ['approval'] : []), ...[...needed].map((c) => `a '${c}' call`)];
      if (needs.length === 0) continue;
      diagnostics.push({
        code: 'bound_gated_tool',
        severity: 'error',
        message:
          `agent '${agent.name}' binds ${binding} to '${name}' (${annotation.capability}), which is refused without ` +
          `${needs.join(' and ')}; the binding acts on the call, not on its result`,
        location: { agent: agent.name, side, binding, tool: name, capability: annotation.capability },
      });
    }
  }
  return diagnostics;
}
