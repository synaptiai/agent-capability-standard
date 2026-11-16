/**
 * Agent manifests of Standard Agents agents (STANDARD 1.2.0 §5.15.1,
 * §5.15.2).
 *
 * An agent's manifest says which ontology capabilities it may exercise, so
 * that a workflow that declares `agents` raises a delegation's checkpoint
 * and approval to what the target may do. In Standard Agents an agent
 * exercises what the tools its prompts offer perform, what the tools they
 * invoke perform (§5.18.4), and what its subagents may: the manifest is
 * derived from the tools' `acs` annotations (their binding records,
 * §5.18.1). A manifest has no member for flags, so its maxima are those of
 * its capabilities. A manifest derived from part of what the agent can call,
 * from annotations the layer does not load (it treats such a tool as an
 * unbound `mutate` at high risk), or from tools whose declared flags exceed
 * their capabilities', would understate its maxima and fail open, so
 * derivation refuses then.
 */
import {
  type AgentManifest,
  agentsApply,
  annotationRecord,
  checkBindings,
  checkTask,
  type DeclaredFlags,
  joinFlags,
  manifestMaxima,
  type SafetyFlags,
} from '@synaptiai/acs-core';
import { ANNOTATION_KEY } from './grounded.js';
import { ONTOLOGY_VERSION, STANDARD_VERSION } from './ontology.js';

type Tools = Record<string, { annotations?: Record<string, unknown> }>;

/**
 * What derivation reads of an agent: its name, the tools its prompts offer,
 * the tools those invoke that its prompts do not offer (Standard Agents'
 * packed helper tools, which a tool calls with `invokeTool`), and the agents
 * it may delegate to.
 */
export interface DerivableAgent {
  name: string;
  tools: Tools;
  invoked?: Tools;
  subagents?: string[];
}

/** A manifest cannot be derived without understating what the agent may do. */
export class ManifestDerivationError extends Error {
  constructor(
    readonly agent: string,
    readonly unannotated: string[],
    readonly missingChildren: string[],
    /** Names a tool's `invokes` lists that neither `tools` nor `invoked` defines. */
    readonly unresolvedInvokes: string[] = [],
    /** Tools whose declared `flags` are stricter than their capabilities' ontology flags. */
    readonly raisedFlags: string[] = [],
    /**
     * Tools whose annotation does not load as a binding record (§5.18.1),
     * with why: a layer treats such a tool as an unbound `mutate` at high
     * risk (§5.18.2), so no manifest can say less of it.
     */
    readonly malformed: { tool: string; problems: string[] }[] = [],
  ) {
    const parts: string[] = [];
    if (unannotated.length > 0) parts.push(`tools without an acs annotation: ${unannotated.join(', ')}`);
    if (malformed.length > 0) {
      parts.push(
        `tools whose acs annotation does not load: ${malformed.map((m) => `${m.tool} (${m.problems.join('; ')})`).join(', ')}`,
      );
    }
    if (missingChildren.length > 0) parts.push(`subagents without a manifest: ${missingChildren.join(', ')}`);
    if (unresolvedInvokes.length > 0) parts.push(`invoked tools not given: ${unresolvedInvokes.join(', ')}`);
    if (raisedFlags.length > 0) {
      parts.push(`tools whose declared flags exceed their capabilities' (a manifest cannot carry them): ${raisedFlags.join(', ')}`);
    }
    super(`cannot derive the manifest of '${agent}': ${parts.join('; ')}`);
    this.name = 'ManifestDerivationError';
  }
}

function majorMinor(version: string): string {
  return version.split('.').slice(0, 2).join('.');
}

/** Whether declared flags raise any of `own` (§5.2.1: a weaker one is ignored). */
function raises(own: SafetyFlags, declared: unknown): boolean {
  if (typeof declared !== 'object' || declared === null) return false;
  const d = declared as DeclaredFlags;
  const joined = joinFlags(own, {
    risk: d.risk ?? own.risk,
    mutation: d.mutation === true,
    requires_checkpoint: d.requires_checkpoint === true,
    requires_approval: d.requires_approval === true,
  });
  return (
    joined.risk !== own.risk ||
    joined.mutation !== own.mutation ||
    joined.requires_checkpoint !== own.requires_checkpoint ||
    joined.requires_approval !== own.requires_approval
  );
}

/**
 * The manifest of `agent`: the capabilities of the tools it offers and of
 * the tools those invoke, transitively (`invokes`, resolved in `tools`, then
 * `invoked`), plus `delegate` and every subagent's capabilities when it has
 * subagents (`children` by name). Each tool's `acs` annotation is loaded as
 * a binding record (`checkBindings`, as the layer loads it), and the
 * capabilities and `invokes` are read from what loads; a control-only tool
 * (`control: true`) performs none. Throws `ManifestDerivationError` when a
 * tool has no annotation, an annotation does not load (the layer would
 * treat the tool as an unbound `mutate` at high risk), a tool invokes one
 * that is not given, a tool's declared `flags` are stricter than the
 * ontology flags of its own capabilities, or a subagent has no entry in
 * `children`. The effective flags an annotation copies are ignored, as a
 * layer ignores them (§5.18.1).
 */
export function deriveAgentManifest(
  agent: DerivableAgent,
  children: Record<string, AgentManifest> = {},
): AgentManifest {
  const lookup = (name: string) =>
    Object.hasOwn(agent.tools, name)
      ? agent.tools[name]
      : agent.invoked !== undefined && Object.hasOwn(agent.invoked, name)
        ? agent.invoked[name]
        : undefined;
  // Every tool the agent can reach, through the names each annotation's
  // `invokes` lists, with the record it carries.
  const records = new Map<string, Record<string, unknown>>();
  const unannotated: string[] = [];
  const unresolved = new Set<string>();
  const queue = Object.keys(agent.tools);
  const seen = new Set(queue);
  for (let name = queue.shift(); name !== undefined; name = queue.shift()) {
    const record = annotationRecord(name, lookup(name)?.annotations?.[ANNOTATION_KEY]);
    if (record === null) {
      unannotated.push(name);
      continue;
    }
    records.set(name, record);
    if (!Array.isArray(record['invokes'])) continue;
    for (const invoked of record['invokes']) {
      if (typeof invoked !== 'string') continue;
      if (lookup(invoked) === undefined) unresolved.add(invoked);
      else if (!seen.has(invoked)) {
        seen.add(invoked);
        queue.push(invoked);
      }
    }
  }
  // Load them as one set, so that a composite's `invokes` resolve.
  const { effective, diagnostics } = checkBindings([...records.values()]);
  const capabilities = new Set<string>();
  const malformed: { tool: string; problems: string[] }[] = [];
  const raised: string[] = [];
  for (const [name, record] of records) {
    const loaded = effective[name];
    if (loaded === undefined) {
      // Not loaded only because what it invokes did not load (V107): that
      // tool is reported, as unannotated, not given or malformed.
      const problems = diagnostics
        .filter((d) => d.severity === 'error' && d.location.tool === name && d.code !== 'V107')
        .map((d) => `${d.code} ${d.message}`);
      if (problems.length > 0) malformed.push({ tool: name, problems });
      continue;
    }
    for (const c of loaded.capabilities) capabilities.add(c);
    if (loaded.control) continue;
    // A capability the ontology lacks leaves the maxima unknown (V101 where
    // the manifest is used): nothing to compare the flags with.
    const maxima = manifestMaxima({ capabilities: loaded.capabilities });
    if (maxima !== null && raises(maxima, record['flags'])) raised.push(name);
  }
  const missingChildren: string[] = [];
  for (const child of agent.subagents ?? []) {
    const manifest = children[child];
    if (manifest === undefined) {
      missingChildren.push(child);
      continue;
    }
    capabilities.add('delegate');
    for (const c of manifest.capabilities) capabilities.add(c);
  }
  if (
    unannotated.length > 0 ||
    malformed.length > 0 ||
    missingChildren.length > 0 ||
    unresolved.size > 0 ||
    raised.length > 0
  ) {
    throw new ManifestDerivationError(
      agent.name,
      unannotated.sort(),
      missingChildren.sort(),
      [...unresolved].sort(),
      raised.sort(),
      malformed.sort((a, b) => (a.tool < b.tool ? -1 : a.tool > b.tool ? 1 : 0)),
    );
  }
  return {
    agent: agent.name,
    standard: majorMinor(STANDARD_VERSION),
    ontology: majorMinor(ONTOLOGY_VERSION),
    capabilities: [...capabilities].sort(),
  };
}

/**
 * The text a host returns as Standard Agents' `subagent_arguments_required`
 * for a task the agent's manifest refuses (§5.15.2), or null when it fits.
 */
export function taskRefusal(manifest: AgentManifest, task: Record<string, unknown> | null | undefined): string | null {
  const { undeclared, missing } = checkTask(manifest, task);
  if (undeclared.length === 0 && missing.length === 0) return null;
  const parts: string[] = [];
  if (missing.length > 0) parts.push(`missing task inputs: ${missing.join(', ')}`);
  if (undeclared.length > 0) parts.push(`undeclared task inputs: ${undeclared.join(', ')}`);
  return `'${manifest.agent}' ${parts.join('; ')}`;
}

/**
 * A workflow's declared agents (§5.15.2): its `agents`, when a list of
 * strings and the workflow targets 1.2 or later; `header` is the catalog
 * file's version header (`null` for none), which the host passes as §11.5
 * requires. In a workflow that targets 1.0 or 1.1, or declares no version,
 * `agents` has no effect, so this is `null` there.
 */
export function declaredAgents(workflow: Record<string, unknown>, header: string | null): string[] | null {
  if (!agentsApply(workflow, header)) return null;
  const agents = workflow['agents'];
  return Array.isArray(agents) && agents.every((a) => typeof a === 'string') ? (agents as string[]) : null;
}
