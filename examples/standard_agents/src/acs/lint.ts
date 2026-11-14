/**
 * A definition-time check of the tools a prompt offers.
 *
 * The workflow validator checks a workflow's steps against the ontology
 * before anything runs. A prompt has no steps, but it does have a fixed list
 * of tools, and two things can be checked from that list alone: every tool is
 * classified, and no tool needs a capability the prompt can never perform.
 */
import { acsAnnotation } from './grounded.js';
import { prerequisites, type CapabilityId } from './ontology.js';

export interface LintDiagnostic {
  /**
   * V102 (MISSING_PREREQUISITE, STANDARD v1.1.0 §9.2): a `requires` edge
   * that cannot be met. `unclassified` is this binding's own: the Standard
   * has no code for a tool outside the ontology.
   */
  code: 'V102' | 'unclassified';
  severity: 'error' | 'warning';
  message: string;
  location: { prompt: string; tool: string; capability?: CapabilityId };
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
