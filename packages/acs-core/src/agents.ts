/**
 * Agent manifests (STANDARD v1.2.0 §5.15.1): what an agent a `delegate`
 * step names may do. Its maxima are derived from the ontology, never
 * stated (`tests/conformance/agents/maxima.json` pins them).
 */
import { CAPABILITIES, type CapabilityId, type SafetyFlags } from './ontology.js';
import { joinFlags, NO_FLAGS } from './flags.js';

/** One task input, in the form of a workflow input (§5.1). */
export interface TaskInput {
  type?: string | string[];
  required?: boolean;
  description?: string;
  [key: string]: unknown;
}

/** `schemas/agent_manifest_schema.yaml#/agent_manifest`. */
export interface AgentManifest {
  agent: string;
  standard: string;
  ontology: string;
  capabilities: string[];
  task?: Record<string, TaskInput>;
  version?: string;
  description?: string;
  [vendor: `x-${string}`]: unknown;
}

/** A manifest's maxima: the highest risk and the OR of the three booleans. */
export type Maxima = SafetyFlags;

function isCapability(id: string): id is CapabilityId {
  return Object.hasOwn(CAPABILITIES, id);
}

/**
 * A manifest's maxima, or with `readOnly` its read-only maxima (over the
 * capabilities whose ontology `mutation` is false); `null` when it lists a
 * capability the ontology does not define.
 */
export function manifestMaxima(manifest: Pick<AgentManifest, 'capabilities'>, readOnly = false): Maxima | null {
  let out: Maxima = { ...NO_FLAGS };
  for (const id of manifest.capabilities) {
    if (!isCapability(id)) return null;
    const node = CAPABILITIES[id];
    if (readOnly && node.mutation) continue;
    out = joinFlags(out, {
      risk: node.risk,
      mutation: node.mutation,
      requires_checkpoint: node.requires_checkpoint,
      requires_approval: node.requires_approval,
    });
  }
  return out;
}

/** The join of several maxima; `null` when any is unknown. */
export function joinMaxima(...maxima: (Maxima | null)[]): Maxima | null {
  let out: Maxima = { ...NO_FLAGS };
  for (const m of maxima) {
    if (m === null) return null;
    out = joinFlags(out, m);
  }
  return out;
}

/**
 * A task against the manifest's declared `task` (§5.15.2): the names it
 * gives that are not declared, and the required inputs it lacks. A
 * manifest that declares no task accepts any.
 */
export function checkTask(
  manifest: Pick<AgentManifest, 'task'>,
  task: Record<string, unknown> | null | undefined,
): { undeclared: string[]; missing: string[] } {
  const declared = manifest.task;
  if (!declared) return { undeclared: [], missing: [] };
  const given = Object.keys(task ?? {});
  return {
    undeclared: given.filter((n) => !Object.hasOwn(declared, n)),
    missing: Object.entries(declared)
      .filter(([n, spec]) => spec.required === true && !given.includes(n))
      .map(([n]) => n),
  };
}

/** `MAJOR.MINOR[.PATCH]`, each part ASCII digits (§11.5). */
function parseVersion(v: string): [number, number] | null {
  const parts = v.split('.');
  if (parts.length < 2 || parts.length > 3 || !parts.every((p) => /^[0-9]+$/.test(p))) return null;
  return [Number(parts[0]), Number(parts[1])];
}

/**
 * The Standard version a workflow targets (§11.5): its `spec_version` when
 * that is a string `MAJOR.MINOR[.PATCH]`, else the catalog file's header
 * (`# Standard version: ...`, which the host read with the catalog and
 * passes, `null` for none) when that parses, else `null`.
 */
export function workflowTarget(workflow: Record<string, unknown>, header: string | null): [number, number] | null {
  const own = workflow['spec_version'];
  const declared = typeof own === 'string' ? parseVersion(own) : null;
  return declared ?? (header === null ? null : parseVersion(header));
}

/**
 * Whether a workflow's `agents` has effect (§5.15.2): it targets 1.2 or
 * later. In a workflow that targets 1.0 or 1.1, or declares no version,
 * `agents` has no effect (W616, or W605), as for a 1.1 consumer.
 */
export function agentsApply(workflow: Record<string, unknown>, header: string | null): boolean {
  const target = workflowTarget(workflow, header);
  return target !== null && (target[0] > 1 || (target[0] === 1 && target[1] >= 2));
}
