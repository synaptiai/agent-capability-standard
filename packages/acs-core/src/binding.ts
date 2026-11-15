/**
 * Tool binding records (STANDARD 1.2.0 §5.18.1 to §5.18.4).
 *
 * A tool binding states which ontology capability a tool performs and which
 * safety flags it declares (`schemas/interop/tool_binding.schema.json`). A
 * record describes; the code that loads it computes the effective flags from
 * its own ontology and enforces them. `checkBindings` loads a set of records
 * and, given the tools a host offers, checks them. It applies the same rules,
 * in the same order and with the same codes and locations, as the Python
 * loader (`grounded_agency.capabilities.bindings`), and both pass the binding
 * fixtures of `tests/conformance/bindings/`.
 *
 * Loading a set of records:
 *
 * 1. Each record is read in full: a member of the wrong type or value, or an
 *    unknown member whose name does not start with `x-`, is S303; a missing
 *    required one S304; such a record is not loaded.
 * 2. Two records for one tool are V110, and neither is loaded.
 * 3. A cited `standard` this package does not support, or an `ontology` of
 *    another major, is V109.
 * 4. A capability the ontology does not define is V101.
 * 5. `invokes`: a cycle is V105, a name that resolves to no loaded binding
 *    V107; the composite is not loaded.
 * 6. The effective flags are the strictest of the declaration, the ontology's
 *    flags of every capability named and, transitively, the effective flags
 *    of every binding invoked. A declared flag weaker than its capabilities'
 *    is W602 and has no effect, except `mutation: false` on a single
 *    `mutation_overridable` capability.
 * 7. The prerequisites are the `requires` sources of the capabilities the
 *    record names (not of its invokes).
 */
import { joinFlags, NO_FLAGS, RISK_LEVELS } from './flags.js';
import {
  CAPABILITIES,
  isCapability,
  ONTOLOGY_VERSION,
  prerequisitesOf,
  SPEC_VERSIONS,
  type CapabilityId,
  type Risk,
  type SafetyFlags,
} from './ontology.js';

/** How approval of a call is counted (§5.18.7): a binding's `approval`. */
export interface BindingApproval {
  min_approvers: number;
  role?: string;
  /** The binding's `approval.expires`, in milliseconds. */
  expires_ms?: number;
}

/** A tool binding record, as `schemas/interop/tool_binding.schema.json` describes it. */
export interface ToolBindingRecord {
  tool: string;
  ontology: string;
  standard?: string;
  capability?: string;
  domain?: string;
  flags?: { risk?: Risk; mutation?: boolean; requires_checkpoint?: boolean; requires_approval?: boolean };
  additional_capabilities?: string[];
  classifier?: string;
  invokes?: string[];
  approval?: { min_approvers?: number; role?: string; expires?: string };
  control?: true;
  destination?: string;
  [vendor: `x-${string}`]: unknown;
}

/** A diagnostic of loading bindings or checking offered tools (§9.8). */
export interface BindingDiagnostic {
  code: string;
  name: string;
  severity: 'error' | 'warning';
  message: string;
  location: { tool: string; capability?: string; field?: string; prerequisite?: string; action?: string };
}

/** A loaded binding: its effective flags and what a layer checks a call by. */
export interface BoundTool extends SafetyFlags {
  /** Every capability the record names, its primary one first; empty for a control-only tool. */
  capabilities: CapabilityId[];
  /** The `requires` sources of those capabilities. */
  prerequisites: CapabilityId[];
  invokes: string[];
  control: boolean;
  domain?: string;
  classifier?: string;
  approval?: BindingApproval;
  destination?: string;
}

const NAMES: Record<string, string> = {
  S303: 'SCHEMA_VALIDATION_FAILED',
  S304: 'MISSING_REQUIRED_FIELD',
  V101: 'UNKNOWN_CAPABILITY',
  V102: 'MISSING_PREREQUISITE',
  V105: 'CIRCULAR_DEPENDENCY',
  V107: 'UNRESOLVED_TARGET',
  V109: 'UNSUPPORTED_SPEC_VERSION',
  V110: 'DUPLICATE_BINDING',
  V111: 'TOOL_NAME_MISMATCH',
  W602: 'SAFETY_FLAG_DOWNGRADE',
  W617: 'UNBOUND_TOOL',
  F506: 'GATED_CONTROL_ACTION',
};

function diagnostic(code: string, message: string, location: BindingDiagnostic['location']): BindingDiagnostic {
  return { code, name: NAMES[code] ?? code, severity: code.startsWith('W') ? 'warning' : 'error', message, location };
}

const MEMBERS = new Set([
  'tool',
  'standard',
  'ontology',
  'destination',
  'capability',
  'domain',
  'flags',
  'additional_capabilities',
  'classifier',
  'invokes',
  'approval',
  'control',
]);
const NOT_WITH_CONTROL = [
  'capability',
  'domain',
  'flags',
  'additional_capabilities',
  'classifier',
  'invokes',
  'approval',
  'destination',
] as const;
const VERSION = /^\d+\.\d+(\.\d+)?$/;
const POINTER = /^(\/([^~/]|~[01])*)*$/;
const RISK_ORDER: Record<Risk, number> = { low: 0, medium: 1, high: 2 };
const MAX_MS = Number.MAX_SAFE_INTEGER;

/**
 * A duration of the §5.10.1 grammar in milliseconds, rounded up (so only a
 * zero duration is 0): `<digits>(ms|s|m|h|d)` or an ISO-8601 day-time
 * duration `P[nD][T[nH][nM][n[.n]S]]`, with at least one component and,
 * after a `T`, at least one time component. `null` when it is not one.
 */
export function parseDuration(text: unknown): number | null {
  if (typeof text !== 'string') return null;
  const short = /^(\d+)(ms|s|m|h|d)$/.exec(text);
  if (short) {
    const per = { ms: 1, s: 1_000, m: 60_000, h: 3_600_000, d: 86_400_000 }[short[2] as 'ms' | 's' | 'm' | 'h' | 'd'];
    const ms = Number(short[1]) * per;
    return Number.isSafeInteger(ms) ? ms : null;
  }
  const iso = /^P(?:(\d+)D)?(T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)(?:\.(\d{1,9}))?S)?)?$/.exec(text);
  if (!iso) return null;
  const [, days, time, hours, minutes, seconds, fraction] = iso;
  if (days === undefined && time === undefined) return null;
  if (time !== undefined && hours === undefined && minutes === undefined && seconds === undefined) return null;
  const whole = (n: string | undefined, scale: number) => (n === undefined ? 0 : Number(n) * scale);
  let ms =
    whole(days, 86_400_000) + whole(hours, 3_600_000) + whole(minutes, 60_000) + whole(seconds, 1_000);
  if (fraction !== undefined) ms += Math.ceil(Number(fraction.padEnd(9, '0')) / 1_000_000);
  return ms <= MAX_MS ? ms : null;
}

interface Parsed {
  tool: string;
  ontology: string;
  standard?: string;
  capability?: string;
  domain?: string;
  flags: { risk?: Risk; mutation?: boolean; requires_checkpoint?: boolean; requires_approval?: boolean };
  additional: string[];
  classifier?: string;
  invokes: string[];
  approval?: BindingApproval;
  control: boolean;
  destination?: string;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Read one record in full, without the ontology (step 1). */
export function parseRecord(record: unknown): { binding: Parsed | null; errors: BindingDiagnostic[] } {
  const errors: BindingDiagnostic[] = [];
  if (!isObject(record)) {
    return {
      binding: null,
      errors: [diagnostic('S303', 'a tool binding must be a JSON object', { tool: '', field: '' })],
    };
  }
  const rawTool = record['tool'];
  const tool = typeof rawTool === 'string' ? rawTool : '';
  const wrong = (field: string, message: string) =>
    errors.push(diagnostic('S303', `tool binding '${tool}': ${message}`, { tool, field }));
  const missing = (field: string, why = '') =>
    errors.push(diagnostic('S304', `tool binding '${tool}' has no '${field}'${why}`, { tool, field }));
  const has = (member: string) => Object.hasOwn(record, member);

  for (const key of Object.keys(record)) {
    if (!MEMBERS.has(key) && !key.startsWith('x-')) wrong(key, `unknown member '${key}' (vendor data starts with 'x-')`);
  }
  if (!has('tool')) missing('tool');
  else if (typeof rawTool !== 'string' || rawTool === '') wrong('tool', "'tool' must be a non-empty string");

  for (const member of ['ontology', 'standard'] as const) {
    if (!has(member)) {
      if (member === 'ontology') missing('ontology');
      continue;
    }
    const value = record[member];
    if (typeof value !== 'string' || !VERSION.test(value)) {
      wrong(member, `'${member}' must be a version MAJOR.MINOR[.PATCH], not ${JSON.stringify(value)}`);
    }
  }
  if (has('destination')) {
    const value = record['destination'];
    if (typeof value !== 'string' || !POINTER.test(value)) wrong('destination', "'destination' must be an RFC 6901 JSON pointer");
  }
  if (has('capability')) {
    const value = record['capability'];
    if (typeof value !== 'string' || value === '') wrong('capability', `'capability' must be a capability id, not ${JSON.stringify(value)}`);
  }
  for (const member of ['domain', 'classifier'] as const) {
    if (has(member)) {
      const value = record[member];
      if (typeof value !== 'string' || value === '') wrong(member, `'${member}' must be a non-empty string`);
    }
  }

  const flags: Parsed['flags'] = {};
  if (has('flags')) {
    const value = record['flags'];
    if (!isObject(value)) wrong('flags', "'flags' must be an object");
    else {
      for (const [key, flag] of Object.entries(value)) {
        const path = `flags/${key}`;
        if (key === 'risk') {
          if (typeof flag !== 'string' || !(RISK_LEVELS as readonly string[]).includes(flag)) {
            wrong(path, `'risk' must be one of ${RISK_LEVELS.join(', ')}`);
          } else flags.risk = flag as Risk;
        } else if (key === 'mutation' || key === 'requires_checkpoint' || key === 'requires_approval') {
          if (typeof flag !== 'boolean') wrong(path, `'${key}' must be true or false, not ${JSON.stringify(flag)}`);
          else flags[key] = flag;
        } else wrong(path, `unknown flag '${key}'`);
      }
    }
  }

  let additional: string[] = [];
  if (has('additional_capabilities')) {
    const value = record['additional_capabilities'];
    if (!Array.isArray(value) || value.length === 0 || !value.every((v) => typeof v === 'string' && v !== '')) {
      wrong('additional_capabilities', "'additional_capabilities' must be a non-empty list of capability ids");
    } else if (new Set(value).size !== value.length) {
      wrong('additional_capabilities', "'additional_capabilities' repeats an id");
    } else additional = value as string[];
  }

  let invokes: string[] = [];
  if (has('invokes')) {
    const value = record['invokes'];
    if (!Array.isArray(value) || !value.every((v) => typeof v === 'string' && v !== '')) {
      wrong('invokes', "'invokes' must be a list of tool names");
    } else if (new Set(value).size !== value.length) {
      wrong('invokes', "'invokes' repeats a name");
    } else invokes = value as string[];
  }

  let approval: BindingApproval | undefined;
  if (has('approval')) {
    const value = record['approval'];
    if (!isObject(value)) wrong('approval', "'approval' must be an object");
    else {
      let ok = true;
      for (const key of Object.keys(value)) {
        if (!['min_approvers', 'role', 'expires'].includes(key)) {
          wrong(`approval/${key}`, `unknown member 'approval.${key}'`);
          ok = false;
        }
      }
      const min = Object.hasOwn(value, 'min_approvers') ? value['min_approvers'] : 1;
      if (typeof min !== 'number' || !Number.isInteger(min) || min < 1) {
        wrong('approval/min_approvers', "'approval.min_approvers' must be an integer of at least 1");
        ok = false;
      }
      const role = value['role'];
      if (role !== undefined && (typeof role !== 'string' || role === '')) {
        wrong('approval/role', "'approval.role' must be a non-empty string");
        ok = false;
      }
      let expires: number | undefined;
      if (Object.hasOwn(value, 'expires')) {
        const ms = parseDuration(value['expires']);
        if (ms === null) {
          wrong('approval/expires', `'approval.expires': ${JSON.stringify(value['expires'])} is not a duration`);
          ok = false;
        } else if (ms <= 0) {
          wrong('approval/expires', "'approval.expires' must be a duration longer than zero");
          ok = false;
        } else expires = ms;
      }
      if (ok) {
        approval = {
          min_approvers: min as number,
          ...(typeof role === 'string' ? { role } : {}),
          ...(expires !== undefined ? { expires_ms: expires } : {}),
        };
      }
    }
  }

  let control = false;
  if (has('control')) {
    if (record['control'] !== true) wrong('control', "'control' must be true when present");
    else {
      control = true;
      for (const member of NOT_WITH_CONTROL) {
        if (has(member)) wrong(member, `a control-only record (control: true) has no '${member}'`);
      }
    }
  }
  if (!control && !has('capability') && !has('control')) missing('capability', ' and is not control-only (control: true)');

  if (errors.length > 0) return { binding: null, errors };
  const str = (member: string) => (typeof record[member] === 'string' ? (record[member] as string) : undefined);
  const binding: Parsed = {
    tool,
    ontology: record['ontology'] as string,
    flags,
    additional,
    invokes,
    control,
  };
  for (const member of ['standard', 'capability', 'domain', 'classifier', 'destination'] as const) {
    const value = str(member);
    if (value !== undefined) binding[member] = value;
  }
  if (approval !== undefined) binding.approval = approval;
  return { binding, errors: [] };
}

function capabilitiesOf(binding: Parsed): string[] {
  return binding.capability === undefined ? [] : [binding.capability, ...binding.additional];
}

/** Steps 3 and 4: the versions a record cites, and its capabilities. */
function checkAgainstOntology(binding: Parsed): BindingDiagnostic[] {
  const out: BindingDiagnostic[] = [];
  const tool = binding.tool;
  if (binding.standard !== undefined) {
    const [major, minor] = binding.standard.split('.');
    if (!(SPEC_VERSIONS as readonly string[]).includes(`${Number(major)}.${Number(minor)}`)) {
      out.push(
        diagnostic(
          'V109',
          `tool binding '${tool}': the document cites standard ${binding.standard}, which is not supported (supported: ${SPEC_VERSIONS.join(', ')})`,
          { tool, field: 'standard' },
        ),
      );
    }
  }
  if (Number(binding.ontology.split('.')[0]) !== Number(ONTOLOGY_VERSION.split('.')[0])) {
    out.push(
      diagnostic(
        'V109',
        `tool binding '${tool}': the document cites ontology ${binding.ontology}, but this implementation uses ontology ${ONTOLOGY_VERSION}; another major is not compatible (§11.6)`,
        { tool, field: 'ontology' },
      ),
    );
  }
  if (out.length > 0) return out;
  for (const capability of capabilitiesOf(binding)) {
    if (!isCapability(capability)) {
      out.push(
        diagnostic('V101', `tool '${tool}' declares capability '${capability}', which the ontology does not define`, {
          tool,
          field: capability === binding.capability ? 'capability' : 'additional_capabilities',
        }),
      );
    }
  }
  return out;
}

/** Step 6 without `invokes`: the record's own flags, and its W602s. */
function ownFlags(binding: Parsed): { flags: SafetyFlags; warnings: BindingDiagnostic[] } {
  const caps = capabilitiesOf(binding) as CapabilityId[];
  let base = NO_FLAGS;
  for (const capability of caps) {
    const node = CAPABILITIES[capability];
    base = joinFlags(base, {
      risk: node.risk,
      mutation: node.mutation,
      requires_checkpoint: node.requires_checkpoint,
      requires_approval: node.requires_approval,
    });
  }
  const declared = binding.flags;
  const warnings: BindingDiagnostic[] = [];
  const downgrade = (field: string, message: string) =>
    warnings.push(
      diagnostic('W602', `tool '${binding.tool}': ${message}`, { tool: binding.tool, capability: caps[0]!, field }),
    );

  let risk = base.risk;
  if (declared.risk !== undefined) {
    if (RISK_ORDER[declared.risk] > RISK_ORDER[risk]) risk = declared.risk;
    else if (RISK_ORDER[declared.risk] < RISK_ORDER[risk]) {
      downgrade(
        'risk',
        `the ontology declares risk=${base.risk} but the tool declares risk=${declared.risk}; the ontology value applies`,
      );
    }
  }
  let mutation = base.mutation;
  if (declared.mutation === true) mutation = true;
  else if (declared.mutation === false && base.mutation) {
    if (caps.length === 1 && CAPABILITIES[caps[0]!].mutation_overridable) mutation = false;
    else {
      downgrade(
        'mutation',
        'the ontology declares mutation=true but the tool declares mutation=false; the ontology value applies (the call is treated as a mutation)',
      );
    }
  }
  const boolean = (flag: 'requires_checkpoint' | 'requires_approval', why: string): boolean => {
    if (declared[flag] === false && base[flag]) {
      downgrade(
        flag,
        `the ontology declares ${flag}=true but the tool declares ${flag}=false; the ontology value applies (${why})`,
      );
    }
    return base[flag] || declared[flag] === true;
  };
  return {
    flags: {
      risk,
      mutation,
      requires_checkpoint: boolean('requires_checkpoint', 'F501 if no checkpoint precedes it'),
      requires_approval: boolean('requires_approval', 'F502 if it is not approved'),
    },
    warnings,
  };
}

/** The strongly connected components of `graph` that hold a cycle (Tarjan). */
function cycles(graph: Map<string, string[]>): string[][] {
  const index = new Map<string, number>();
  const low = new Map<string, number>();
  const onStack = new Set<string>();
  const stack: string[] = [];
  const found: string[][] = [];
  let counter = 0;
  const visit = (node: string) => {
    index.set(node, counter);
    low.set(node, counter);
    counter += 1;
    stack.push(node);
    onStack.add(node);
    for (const target of graph.get(node) ?? []) {
      if (!graph.has(target)) continue;
      if (!index.has(target)) {
        visit(target);
        low.set(node, Math.min(low.get(node)!, low.get(target)!));
      } else if (onStack.has(target)) {
        low.set(node, Math.min(low.get(node)!, index.get(target)!));
      }
    }
    if (low.get(node) === index.get(node)) {
      const component: string[] = [];
      for (;;) {
        const member = stack.pop()!;
        onStack.delete(member);
        component.push(member);
        if (member === node) break;
      }
      if (component.length > 1 || (graph.get(node) ?? []).includes(node)) {
        found.push(component.sort((a, b) => index.get(a)! - index.get(b)!));
      }
    }
  };
  for (const node of graph.keys()) if (!index.has(node)) visit(node);
  return found;
}

export interface CheckBindingsOptions {
  /**
   * Each name the host offers a tool under, mapped to the `tool` of the
   * record it carries, or null for none (§5.18.2). Without it, offered tools
   * are not checked.
   */
  offered?: Record<string, string | null>;
  /** Host actions taken whenever a tool is called, such as ending the turn. */
  hostActions?: readonly { action: string; tool: string }[];
  /** The host takes checkpoints itself, so `checkpoint` counts as performed. */
  hostTakesCheckpoints?: boolean;
  /** Bindings loaded earlier, which an `invokes` name may resolve to. */
  known?: Record<string, BoundTool>;
}

/**
 * Load a set of tool binding records and, given `offered`, check the tools a
 * host offers (§5.18.1 to §5.18.4).
 *
 * Returns the loaded bindings by tool and every diagnostic: errors for the
 * records that did not load, W602 for those that did, and the offered-tool
 * checks (W617, V111, V102, F506).
 */
export function checkBindings(
  records: readonly unknown[],
  options: CheckBindingsOptions = {},
): { effective: Record<string, BoundTool>; diagnostics: BindingDiagnostic[] } {
  const known = options.known ?? {};
  const diagnostics: BindingDiagnostic[] = [];
  const parsed: Parsed[] = [];
  for (const record of records) {
    const { binding, errors } = parseRecord(record);
    diagnostics.push(...errors);
    if (binding) parsed.push(binding);
  }

  // 2. Two records for one tool, a record that could not be read included.
  const counts = new Map<string, number>();
  for (const record of records) {
    const tool = isObject(record) ? record['tool'] : undefined;
    if (typeof tool === 'string' && tool !== '') counts.set(tool, (counts.get(tool) ?? 0) + 1);
  }
  const candidates = new Map<string, Parsed>();
  for (const binding of parsed) {
    if ((counts.get(binding.tool) ?? 1) > 1) {
      diagnostics.push(
        diagnostic('V110', `two tool bindings name the tool '${binding.tool}'; neither is loaded`, {
          tool: binding.tool,
          field: 'tool',
        }),
      );
      continue;
    }
    const problems = checkAgainstOntology(binding);
    if (problems.length > 0) {
      diagnostics.push(...problems);
      continue;
    }
    candidates.set(binding.tool, binding);
  }

  // 5. invokes: cycles (V105), then names that resolve to nothing (V107).
  const graph = new Map([...candidates].map(([tool, b]) => [tool, [...b.invokes]]));
  for (const component of cycles(graph)) {
    for (const tool of component) {
      diagnostics.push(
        diagnostic(
          'V105',
          `tool '${tool}' is part of an invokes cycle (${[...component, component[0]].join(' -> ')}); it is not loaded`,
          { tool, field: 'invokes' },
        ),
      );
      candidates.delete(tool);
    }
  }
  for (let changed = true; changed; ) {
    changed = false;
    for (const [tool, binding] of [...candidates]) {
      const unresolved = binding.invokes.filter((name) => !candidates.has(name) && !Object.hasOwn(known, name));
      if (unresolved.length === 0) continue;
      for (const name of unresolved) {
        diagnostics.push(
          diagnostic('V107', `tool '${tool}' invokes '${name}', which no loaded binding of the set names; it is not loaded`, {
            tool,
            field: 'invokes',
          }),
        );
      }
      candidates.delete(tool);
      changed = true;
    }
  }

  // 6. Effective flags, then the invoked bindings', memoised.
  const own = new Map<string, SafetyFlags>();
  for (const [tool, binding] of candidates) {
    if (binding.control) {
      own.set(tool, NO_FLAGS);
      continue;
    }
    const { flags, warnings } = ownFlags(binding);
    own.set(tool, flags);
    diagnostics.push(...warnings);
  }
  const resolved = new Map<string, SafetyFlags>();
  const resolve = (tool: string): SafetyFlags => {
    const done = resolved.get(tool);
    if (done) return done;
    const binding = candidates.get(tool);
    if (!binding) {
      const k = known[tool]!;
      return { risk: k.risk, mutation: k.mutation, requires_checkpoint: k.requires_checkpoint, requires_approval: k.requires_approval };
    }
    let flags = own.get(tool)!;
    for (const name of binding.invokes) flags = joinFlags(flags, resolve(name));
    resolved.set(tool, flags);
    return flags;
  };

  // 7. Prerequisites of the capabilities each record names.
  const effective: Record<string, BoundTool> = {};
  for (const [tool, binding] of candidates) {
    const capabilities = capabilitiesOf(binding) as CapabilityId[];
    effective[tool] = {
      ...resolve(tool),
      capabilities,
      prerequisites: prerequisitesOf(capabilities),
      invokes: [...binding.invokes],
      control: binding.control,
      ...(binding.domain !== undefined ? { domain: binding.domain } : {}),
      ...(binding.classifier !== undefined ? { classifier: binding.classifier } : {}),
      ...(binding.approval !== undefined ? { approval: binding.approval } : {}),
      ...(binding.destination !== undefined ? { destination: binding.destination } : {}),
    };
  }

  if (options.offered !== undefined || options.hostActions !== undefined) {
    diagnostics.push(...checkOffered(options.offered ?? {}, effective, options));
  }
  return { effective, diagnostics };
}

/** §5.18.2: the tools a host offers, against the loaded bindings. */
function checkOffered(
  offered: Record<string, string | null>,
  effective: Record<string, BoundTool>,
  options: CheckBindingsOptions,
): BindingDiagnostic[] {
  const out: BindingDiagnostic[] = [];
  const bound = (name: string): BoundTool | undefined => {
    const carried = Object.hasOwn(offered, name) ? offered[name] : name;
    return carried === name ? effective[name] : undefined;
  };
  const performable = new Set<string>();
  let anyCapability = false;
  for (const name of Object.keys(offered)) {
    const tool = bound(name);
    if (!tool || tool.control) continue;
    for (const capability of tool.capabilities) performable.add(capability);
    if (tool.classifier !== undefined) anyCapability = true;
  }
  if (options.hostTakesCheckpoints) performable.add('checkpoint');

  for (const [name, carried] of Object.entries(offered)) {
    if (carried !== null && carried !== name) {
      out.push(
        diagnostic(
          'V111',
          `the host offers '${name}' with the binding of '${carried}'; a binding's tool must be the name the tool is offered under`,
          { tool: name, field: 'tool' },
        ),
      );
      continue;
    }
    const tool = bound(name);
    if (!tool) {
      out.push(
        diagnostic('W617', `the host offers '${name}', which has no loaded binding; its calls are treated as the strictest case`, {
          tool: name,
        }),
      );
      continue;
    }
    if (tool.control || anyCapability) continue;
    const needed = [...tool.prerequisites].sort();
    if (tool.requires_checkpoint && !needed.includes('checkpoint')) needed.push('checkpoint');
    for (const capability of needed) {
      if (!performable.has(capability)) {
        out.push(
          diagnostic(
            'V102',
            `tool '${name}' (${tool.capabilities[0]}) requires '${capability}', and no offered tool performs it, so its calls could never run`,
            { tool: name, capability: tool.capabilities[0]!, prerequisite: capability },
          ),
        );
      }
    }
  }

  for (const { action, tool: name } of options.hostActions ?? []) {
    const tool = bound(name);
    if (tool && (tool.control || !(tool.prerequisites.length > 0 || tool.requires_checkpoint || tool.requires_approval))) {
      continue;
    }
    const why = tool ? 'can be refused for want of a checkpoint, approval or a prerequisite' : 'is unbound';
    out.push(
      diagnostic(
        'F506',
        `host action '${action}' takes effect whenever '${name}' is called, and '${name}' ${why}; tie it to a control-only tool`,
        { tool: name, action },
      ),
    );
  }
  return out;
}

/** The record members an `acs` annotation carries; the rest are copies or the annotation's own. */
const RECORD_MEMBERS = [
  'standard',
  'ontology',
  'capability',
  'domain',
  'flags',
  'additional_capabilities',
  'classifier',
  'invokes',
  'approval',
  'control',
  'destination',
] as const;

/**
 * Read a Standard Agents `acs` annotation as a tool binding record (§5.18.1:
 * an annotation is a carrier). `tool` is the name the tool is offered under;
 * the copies an annotation holds (`layer`, the effective flags) are ignored.
 * Null for a value that is not an object.
 */
export function annotationRecord(name: string, annotation: unknown): Record<string, unknown> | null {
  if (!isObject(annotation)) return null;
  const record: Record<string, unknown> = { tool: name };
  for (const member of RECORD_MEMBERS) {
    if (Object.hasOwn(annotation, member)) record[member] = annotation[member];
  }
  for (const [key, value] of Object.entries(annotation)) {
    if (key.startsWith('x-')) record[key] = value;
  }
  return record;
}
