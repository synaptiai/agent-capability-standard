/**
 * Types of what the reference core answers through its WebAssembly
 * interface (`./wasm`): reports and diagnostics (Standard 1.2.0 section 9),
 * and the actions, responses and snapshots of the host protocol (section
 * 5.19, `schemas/host_protocol.schema.json`).
 */
import type { Json } from './canonical.js';

/** One finding (section 9.8). */
export interface Diagnostic {
  code: string;
  name: string;
  severity: 'error' | 'warning';
  message: string;
  location: Record<string, Json>;
  suggestion?: string;
}

/** The result of validating a catalog or checking profiles. */
export interface Report {
  diagnostics: Diagnostic[];
  suggestions: Json[];
}

/** What the core reports about itself (`version`). */
export interface CoreVersion {
  /** The core crate's version. */
  core: string;
  /** The Standard version the core implements. */
  standard: string;
  /** The Standard versions a workflow may target (section 11.5). */
  spec_versions: string[];
  /** The ontology major the core reads (section 11.6). */
  ontology_major: number;
}

/** The kinds of action the executor asks a host for (section 5.19.1). */
export type ActionKind =
  | 'InvokeCapability'
  | 'CreateCheckpoint'
  | 'Rollback'
  | 'RequestApproval'
  | 'RecheckSource'
  | 'AwaitEvent'
  | 'Sleep'
  | 'Completed'
  | 'Failed';

/** An action: `id`, the workflows of the nested runs, its kind and the
 * members of that kind (`schemas/host_protocol.schema.json#/$defs/action`). */
export interface Action {
  id: number;
  frame: string[];
  kind: ActionKind;
  [member: string]: Json;
}

/** A host's answer to the pending action (section 5.19.1). */
export type CoreResponse = { kind: string; [member: string]: Json };

/** A run's saved state (section 5.19.4). */
export interface Snapshot {
  state: string;
  sha256: string;
  hmac: string | null;
}

/** The effective flags of a step or call under domain profiles (section
 * 5.21.3). */
export interface ProfileFlags {
  risk: 'low' | 'medium' | 'high';
  mutation: boolean;
  requires_checkpoint: boolean;
  requires_approval: boolean;
  /** A person must decide, each time. */
  person: boolean;
}

/** The rules domain profiles put in force besides flags (section 5.21.3). */
export interface ProfilePolicy {
  minimum_confidence: number | null;
  grounding: { require: string[]; kinds: string[] | null }[];
  destinations: string[][];
  trust_weights: Record<string, number>;
}
