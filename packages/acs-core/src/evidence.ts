/**
 * Evidence anchors and grounding (STANDARD v1.2.0 §3.1, §5.20, §6.5, §6.6).
 *
 * An evidence anchor is `{ref, kind, timestamp?, excerpt?, digest?}`, its
 * kind one of {@link ANCHOR_KINDS} or a vendor kind `x-...`. A grounding
 * policy names the capabilities whose outputs are checked; {@link
 * checkGrounding} is §5.20's check of one output, which the vectors of
 * `tests/conformance/grounding/check.json` pin for this package, the Rust
 * core and the Python package alike.
 */
import type { Json } from './canonical.js';
import { type CapabilityId, isCapability } from './ontology.js';

/** The evidence-anchor kinds of §6.5. */
export const ANCHOR_KINDS = ['file', 'url', 'tool', 'log', 'sensor', 'human_note', 'api', 'record'] as const;

/** The inference methods of §4.1.1. */
export const INFERENCE_METHODS = [
  'model_knowledge',
  'deduction',
  'induction',
  'abduction',
  'analogy',
  'statistical',
  'simulation',
  'assumption',
] as const;

/** A §6.5 kind: one of {@link ANCHOR_KINDS}, or a vendor kind. */
export type AnchorKind = (typeof ANCHOR_KINDS)[number] | `x-${string}`;

/** An evidence anchor (§6.5). Other members may appear; a producer's own start with `x-`. */
export type EvidenceAnchor = {
  ref: string;
  kind: AnchorKind;
  timestamp?: string | null;
  excerpt?: string | null;
  digest?: string;
};

const VENDOR = /^x-[a-z0-9][a-z0-9_.-]*$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;

/** Whether `kind` is a §6.5 kind. */
export function isKind(kind: unknown): kind is AnchorKind {
  return typeof kind === 'string' && ((ANCHOR_KINDS as readonly string[]).includes(kind) || VENDOR.test(kind));
}

/** Whether `method` is an inference method of §4.1.1's vocabulary (or a vendor one). */
export function isMethod(method: unknown): boolean {
  return (
    typeof method === 'string' && ((INFERENCE_METHODS as readonly string[]).includes(method) || VENDOR.test(method))
  );
}

/** Whether `digest` has §6.5's form: `sha256:` and 64 lowercase hexadecimal digits. */
export function isDigest(digest: unknown): digest is string {
  return typeof digest === 'string' && DIGEST.test(digest);
}

function isObject(v: unknown): v is { [key: string]: unknown } {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

/**
 * Whether `value` is an evidence anchor: an object whose `ref` is a
 * non-empty string, whose `kind` is a §6.5 kind and whose `digest`, when
 * present, has §6.5's form. Anything else in an `evidence_anchors` list is
 * a deprecated legacy form.
 */
export function isEvidenceAnchor(value: unknown): value is EvidenceAnchor {
  return (
    isObject(value) &&
    typeof value['ref'] === 'string' &&
    value['ref'] !== '' &&
    isKind(value['kind']) &&
    (!('digest' in value) || isDigest(value['digest']))
  );
}

/** A grounding policy (§5.20). */
export interface GroundingPolicy {
  /** The capabilities whose outputs are checked. */
  require: readonly CapabilityId[];
  /** Only anchors of these kinds count. */
  kinds?: readonly string[];
  /** Count only anchors whose availability is established. */
  attested?: boolean;
}

function strings(value: unknown, at: string): string[] {
  if (!Array.isArray(value) || value.length === 0 || !value.every((x) => typeof x === 'string')) {
    throw new Error(`S303 SCHEMA_VALIDATION_FAILED: ${at} must be a non-empty list of strings`);
  }
  const items = value as string[];
  const twice = items.findIndex((x, i) => items.indexOf(x) !== i);
  if (twice >= 0) {
    throw new Error(`S303 SCHEMA_VALIDATION_FAILED: ${at}[${twice}] '${items[twice]}' is listed twice`);
  }
  return items;
}

/**
 * One policy or a list of them, checked and frozen. Every host-side policy
 * is validated against the ontology (§5.20): an id it does not define
 * throws (V101), as does an empty or repeated `require`, an empty or
 * repeated `kinds`, a kind outside §6.5's vocabulary, and an `attested` that
 * is not a boolean: TypeScript types do not reach a JavaScript caller or a
 * JSON configuration, and a typo must not silently turn a check off.
 */
export function groundingPolicies(value: GroundingPolicy | readonly GroundingPolicy[]): readonly GroundingPolicy[] {
  const list: readonly unknown[] = Array.isArray(value) ? value : [value];
  return Object.freeze(
    list.map((p, i) => {
      if (!isObject(p)) throw new Error(`S303 SCHEMA_VALIDATION_FAILED: grounding[${i}] must be an object`);
      const require = strings(p['require'], `grounding[${i}].require`);
      const unknown = require.findIndex((id) => !isCapability(id));
      if (unknown >= 0) {
        throw new Error(
          `V101 UNKNOWN_CAPABILITY: grounding[${i}].require[${unknown}] '${require[unknown]}' is not a capability of the ontology`,
        );
      }
      const policy: GroundingPolicy = { require: Object.freeze([...require]) as readonly CapabilityId[] };
      if (p['kinds'] !== undefined) {
        const kinds = strings(p['kinds'], `grounding[${i}].kinds`);
        const bad = kinds.findIndex((k) => !isKind(k));
        if (bad >= 0) {
          throw new Error(
            `S303 SCHEMA_VALIDATION_FAILED: grounding[${i}].kinds[${bad}] '${kinds[bad]}' is not an evidence anchor kind (§6.5)`,
          );
        }
        policy.kinds = Object.freeze([...kinds]);
      }
      if (p['attested'] !== undefined) {
        if (typeof p['attested'] !== 'boolean') {
          throw new Error(`S303 SCHEMA_VALIDATION_FAILED: grounding[${i}].attested must be a boolean`);
        }
        policy.attested = p['attested'];
      }
      return Object.freeze(policy);
    }),
  );
}

/** One path segment of a reference (§5.3). */
export type Segment =
  | { field: string }
  | { index: number }
  | { slice: [number | null, number | null] };

/** A parsed reference body: its root, path and annotation (§5.3). */
export interface Reference {
  root: string;
  path: Segment[];
  annotation: string | null;
}

const IDENT_START = /[A-Za-z_]/;
const IDENT = /[A-Za-z0-9_-]/;

/**
 * Parse a reference body as §5.3 writes it inside `${` and `}`
 * (`search_out.results[0:3]`, `r.data: object`), as the reference
 * validator does. Throws for a body that is not one.
 */
export function parseRef(body: string): Reference {
  let depth = 0;
  let split = -1;
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (c === '[') depth++;
    else if (c === ']') depth--;
    else if (c === ':' && depth === 0) {
      split = i;
      break;
    }
  }
  let annotation: string | null = null;
  let pathPart = body;
  if (split >= 0) {
    annotation = body.slice(split + 1).trim();
    if (annotation === '') throw new Error(`empty type annotation in '\${${body}}'`);
    pathPart = body.slice(0, split);
  }
  const p = pathPart.trim();
  const bad = (why: string): never => {
    throw new Error(`malformed reference '\${${body}}': ${why}`);
  };
  if (p === '' || !IDENT_START.test(p[0] ?? '')) bad('expected an identifier');
  let end = 0;
  while (end < p.length && IDENT.test(p[end] ?? '')) end++;
  const root = p.slice(0, end);
  const path: Segment[] = [];
  let rest = p.slice(end);
  const num = (t: string): number | null => {
    if (t === '') return null;
    if (!/^[0-9]+$/.test(t)) bad(`bad index '${t}'`);
    if (t.length > 1 && t.startsWith('0')) bad(`leading zeros in index '${t}'`);
    const n = Number(t);
    if (!Number.isSafeInteger(n)) bad('index too large');
    return n;
  };
  while (rest !== '') {
    if (rest.startsWith('.')) {
      const r = rest.slice(1);
      let n = 0;
      while (n < r.length && IDENT.test(r[n] ?? '')) n++;
      const name = r.slice(0, n);
      if (name === '' || !IDENT_START.test(name[0] ?? '')) bad("expected a field name after '.'");
      path.push({ field: name });
      rest = r.slice(n);
    } else if (rest.startsWith('[')) {
      const r = rest.slice(1);
      const close = r.indexOf(']');
      if (close < 0) bad("unclosed '['");
      const inner = r.slice(0, close);
      const colon = inner.indexOf(':');
      if (colon >= 0) {
        path.push({ slice: [num(inner.slice(0, colon)), num(inner.slice(colon + 1))] });
      } else {
        const n = num(inner);
        if (n === null) bad('empty index');
        path.push({ index: n as number });
      }
      rest = r.slice(close + 1);
    } else {
      bad(`unexpected '${rest}'`);
    }
  }
  return { root, path, annotation };
}

function segmentCovers(b: Segment, c: Segment): boolean {
  if ('field' in b) return 'field' in c && c.field === b.field;
  if ('index' in b) return 'index' in c && c.index === b.index;
  const [start, end] = b.slice;
  if ('index' in c) return (start ?? 0) <= c.index && (end === null || c.index < end);
  if ('slice' in c) {
    const [from, to] = c.slice;
    return (start ?? 0) <= (from ?? 0) && (end === null || (to !== null && to <= end));
  }
  return false;
}

/**
 * Whether the reference `bound` covers `cited` (§5.20): the same root, and
 * each segment of `bound`'s path matches `cited`'s at the same position (a
 * bound slice matches an index or a slice within it); `cited` may go on.
 */
export function covers(bound: Reference, cited: Reference): boolean {
  return (
    bound.root === cited.root &&
    cited.path.length >= bound.path.length &&
    bound.path.every((b, i) => segmentCovers(b, cited.path[i] as Segment))
  );
}

function bodyOf(r: Reference): string {
  return (
    r.root +
    r.path
      .map((s) =>
        'field' in s ? `.${s.field}` : 'index' in s ? `[${s.index}]` : `[${s.slice[0] ?? ''}:${s.slice[1] ?? ''}]`,
      )
      .join('')
  );
}

/** What {@link checkGrounding} found. */
export interface GroundingResult {
  status: 'grounded' | 'inferred' | 'refused';
  code: 'F505' | null;
  message: string;
  /** Anchors that count (0 for a refused output). */
  counted: number;
  /** Items that are not evidence anchors (0 for a refused output). */
  legacy: number;
  /** Anchors whose availability is not established (0 for a refused output). */
  unattested: number;
}

/** The context of one output: the references its step binds (for a call, its argument names) and the host's `evidence_seen`. */
export interface GroundingContext {
  bound?: readonly string[];
  /** Absent (`undefined` or `null`) attests nothing; `[]` attests that nothing was seen. */
  seen?: readonly string[] | null;
}

const plural = (n: number): string => (n === 1 ? '' : 's');

/**
 * §5.20's check of one output against a policy's `kinds` and `attested`
 * (whether the policy requires the capability is the caller's question).
 * Throws for a bound reference that is not a reference body.
 */
export function checkGrounding(
  output: unknown,
  policy: Pick<GroundingPolicy, 'kinds' | 'attested'>,
  ctx: GroundingContext = {},
): GroundingResult {
  const bound = (ctx.bound ?? []).map((b, i) => {
    const r = parseRef(b);
    if (r.annotation !== null || b.trim() !== b) {
      throw new Error(`bound[${i}]: '${b}' is not a reference body (no annotation or spaces)`);
    }
    return r;
  });
  const seen = ctx.seen ?? null;
  const refused = (message: string): GroundingResult => ({
    status: 'refused',
    code: 'F505',
    message,
    counted: 0,
    legacy: 0,
    unattested: 0,
  });
  const items = isObject(output) ? output['evidence_anchors'] : undefined;
  if (!Array.isArray(items)) return refused('evidence_anchors is not a list (§4.1.1)');
  let counted = 0;
  let legacy = 0;
  let excluded = 0;
  let unattested = 0;
  let withheld = 0;
  for (const [i, item] of items.entries()) {
    const ref = isObject(item) && typeof item['ref'] === 'string' ? item['ref'] : undefined;
    const kind = isObject(item) && typeof item['kind'] === 'string' ? item['kind'] : undefined;
    let established: boolean;
    if (ref !== undefined && ref.startsWith('acs:')) {
      if (kind !== 'record') {
        const k = kind === undefined ? 'no kind' : `kind '${kind}'`;
        return refused(
          `evidence_anchors[${i}] cites a workflow value ('${ref}') with ${k}; an acs: anchor is of kind record (§6.5)`,
        );
      }
      let cited: Reference;
      try {
        cited = parseRef(ref.slice(4));
      } catch {
        return refused(`evidence_anchors[${i}] cites '${ref}', whose rest is not a reference body (§5.3) (§6.5)`);
      }
      if (cited.annotation !== null) {
        return refused(`evidence_anchors[${i}] cites '${ref}', whose rest is not a reference body (§5.3) (§6.5)`);
      }
      if (!bound.some((b) => covers(b, cited))) {
        const binds =
          bound.length === 0 ? 'no reference is bound' : `the bound references are ${bound.map(bodyOf).join(', ')}`;
        return refused(
          `evidence_anchors[${i}] cites '${ref}', which no reference bound for the output's producer covers (${binds}) (§3.1, §5.20)`,
        );
      }
      established = true;
    } else if (isEvidenceAnchor(item)) {
      if (seen !== null && !seen.includes(item.ref)) {
        return refused(
          `evidence_anchors[${i}] cites '${item.ref}', which the host's evidence_seen does not list: its producer did not have it (§3.1, §5.20)`,
        );
      }
      established = seen !== null;
    } else {
      legacy++;
      continue;
    }
    if (!established) unattested++;
    if (policy.kinds !== undefined && !policy.kinds.includes(kind ?? '')) excluded++;
    else if (policy.attested === true && !established) withheld++;
    else counted++;
  }
  if (counted > 0) return { status: 'grounded', code: null, message: '', counted, legacy, unattested };
  const out = output as { [key: string]: unknown };
  const method = out['inference_method'];
  const confidence = out['confidence'];
  const methodOk = isMethod(method);
  const confidenceOk = typeof confidence === 'number' && confidence >= 0 && confidence <= 1;
  if (methodOk && confidenceOk) return { status: 'inferred', code: null, message: '', counted, legacy, unattested };
  const why: string[] = [];
  if (items.length === 0) why.push('it has no evidence anchors');
  if (legacy > 0) {
    why.push(
      legacy === 1
        ? '1 item that is not an evidence anchor, which does not count'
        : `${legacy} items that are not evidence anchors, which do not count`,
    );
  }
  if (excluded > 0) why.push(`${excluded} anchor${plural(excluded)} of kinds the policy does not list`);
  if (withheld > 0) why.push(`${withheld} anchor${plural(withheld)} whose availability is not established`);
  const marking: string[] = [];
  if (method === undefined) marking.push('no inference_method');
  else if (!methodOk) marking.push(`an inference_method ${JSON.stringify(method)} outside §4.1.1's vocabulary`);
  if (confidence === undefined) marking.push('no confidence');
  else if (!confidenceOk) marking.push(`a confidence ${JSON.stringify(confidence)} that is not from 0 to 1`);
  return refused(
    `no evidence anchor counts toward the grounding policy (${why.join('; ')}), and the output is not marked inferred: it has ${marking.join(' and ')} (an inference_method of §4.1.1's vocabulary and a confidence from 0 to 1, §3.1)`,
  );
}

/**
 * The `ref` of every evidence anchor inside a JSON value (a call's
 * arguments): what a call received, for `evidence_seen` (§5.20). Never a
 * stored trace or history: a ref there was seen by an earlier request.
 */
export function refsIn(value: Json): string[] {
  const out: string[] = [];
  const walk = (v: unknown): void => {
    if (Array.isArray(v)) v.forEach(walk);
    else if (isObject(v)) {
      if (isEvidenceAnchor(v) && !out.includes(v.ref)) out.push(v.ref);
      Object.values(v).forEach(walk);
    }
  };
  walk(value);
  return out;
}

/** The correlation members of an evidence record or a notification (§6.6). */
export interface EvidenceCorrelation {
  run_id?: string;
  frame?: string[];
  step?: number;
  capability?: string;
  tool?: string;
  call_id?: string;
}

/** An evidence record (§6.6, `schemas/interop/evidence.schema.json`). */
export interface EvidenceRecord extends EvidenceCorrelation {
  record_id: string;
  anchor: EvidenceAnchor;
  recorded_at: string;
  metadata?: { [key: string]: Json };
}

/** The `acs.evidence_recorded` notification (§6.6): one of `record_ids`, `event_id` or `action_ids`. */
export type EvidenceRecorded = EvidenceCorrelation & {
  type: 'acs.evidence_recorded';
  anchors: Array<{ ref: string; kind: AnchorKind; digest?: string }>;
  recorded_at: string;
} & ({ record_ids: string[] } | { event_id: string } | { action_ids: string[] });

/** What an evidence store states about itself (§6.6). */
export interface StoreInfo {
  durability: 'memory' | 'session' | 'durable';
  bounded: boolean;
  count?: number;
  removed?: number;
  retention?: string;
}
