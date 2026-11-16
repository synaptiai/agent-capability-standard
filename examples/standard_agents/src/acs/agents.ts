/**
 * Agent manifests of Standard Agents agents (STANDARD 1.2.0 §5.15.1,
 * §5.15.2).
 *
 * An agent's manifest says which ontology capabilities it may exercise, so
 * that a workflow that declares `agents` raises a delegation's checkpoint
 * and approval to what the target may do. In Standard Agents an agent
 * exercises what the tools its prompts offer perform, and what its
 * subagents may: the manifest is derived from the tools' `acs` annotations
 * (their binding records, §5.18.1). A manifest derived from part of what
 * the agent can call would understate its maxima and fail open, so
 * derivation refuses when any offered tool other than a control-only one is
 * unannotated, or a subagent's manifest is missing.
 */
import { type AgentManifest, checkTask } from '@synaptiai/acs-core';
import { ANNOTATION_KEY } from './grounded.js';
import { ONTOLOGY_VERSION, STANDARD_VERSION } from './ontology.js';

type Tools = Record<string, { annotations?: Record<string, unknown> }>;

/** What derivation reads of an agent: its name, the tools its prompts offer, and the agents it may delegate to. */
export interface DerivableAgent {
  name: string;
  tools: Tools;
  subagents?: string[];
}

/** A manifest cannot be derived without understating what the agent may do. */
export class ManifestDerivationError extends Error {
  constructor(
    readonly agent: string,
    readonly unannotated: string[],
    readonly missingChildren: string[],
  ) {
    const parts: string[] = [];
    if (unannotated.length > 0) parts.push(`tools without an acs annotation: ${unannotated.join(', ')}`);
    if (missingChildren.length > 0) parts.push(`subagents without a manifest: ${missingChildren.join(', ')}`);
    super(`cannot derive the manifest of '${agent}': ${parts.join('; ')}`);
    this.name = 'ManifestDerivationError';
  }
}

function majorMinor(version: string): string {
  return version.split('.').slice(0, 2).join('.');
}

/**
 * The manifest of `agent`: the capabilities of the tools it offers (each
 * annotation's `capability` and `additional_capabilities`), plus `delegate`
 * and every subagent's capabilities when it has subagents (`children` by
 * name). Throws `ManifestDerivationError` when a tool other than a
 * control-only one (`control: true`) has no annotation, or a subagent has
 * no entry in `children`.
 */
export function deriveAgentManifest(
  agent: DerivableAgent,
  children: Record<string, AgentManifest> = {},
): AgentManifest {
  const capabilities = new Set<string>();
  const unannotated: string[] = [];
  for (const [name, tool] of Object.entries(agent.tools)) {
    const annotation = tool.annotations?.[ANNOTATION_KEY];
    if (typeof annotation !== 'object' || annotation === null) {
      unannotated.push(name);
      continue;
    }
    const record = annotation as { capability?: unknown; additional_capabilities?: unknown; control?: unknown };
    if (record.control === true) continue;
    if (typeof record.capability !== 'string') {
      unannotated.push(name);
      continue;
    }
    capabilities.add(record.capability);
    if (Array.isArray(record.additional_capabilities)) {
      for (const c of record.additional_capabilities) if (typeof c === 'string') capabilities.add(c);
    }
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
  if (unannotated.length > 0 || missingChildren.length > 0) {
    throw new ManifestDerivationError(agent.name, unannotated.sort(), missingChildren.sort());
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

/** A workflow's declared agents (§5.15.2): its `agents`, when a list of strings. */
export function declaredAgents(workflow: Record<string, unknown>): string[] | null {
  const agents = workflow['agents'];
  return Array.isArray(agents) && agents.every((a) => typeof a === 'string') ? (agents as string[]) : null;
}
