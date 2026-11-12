// Data for the Standard's site-drawn figures in chapters 4 and 5 (visual spec
// 3.9): capability fields, the layer model, the safety-critical capabilities,
// step anatomy, the anatomy of a reference, annotation types, gate outcomes
// and failure actions. Each reads the Standard's own section (a table, fence
// or sentence) or the catalog schema, and fails when the two disagree. Each
// figure's caption is written here, so the page and its Markdown copy match.
import type { List, ListItem, Table } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { loadCatalogSchema, type CatalogSchema, type SchemaSlot } from '../data/catalog-schema';
import { loadOntology, type Capability, type Ontology } from '../data/ontology';
import { loadVersions } from '../data/versions';
import { referenceRoots } from '../data/workflows';
import { readRepoFile } from './repo';
import { sectionBlocks, sectionFence, sectionTableByHeader, tableCodes, tableRows } from './md-sections';
import { typeGlyphs } from './views';

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const list = (xs: string[]) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`);

/** The current Standard's path and text. */
export function currentStandardText(): { source: string; text: string } {
  const source = loadVersions().standard.current.source;
  return { source, text: readRepoFile(source) };
}

// ------------------------------------------------------- F-S3 layer model

export function layerModelCaption(o: Ontology = loadOntology()): string {
  const sizes = o.layers.map((l) => l.capabilities.length);
  const big = o.layers.filter((l) => l.capabilities.length === Math.max(...sizes)).map((l) => l.id);
  const small = o.layers.filter((l) => l.capabilities.length === Math.min(...sizes)).map((l) => l.id);
  return `${plural(o.capabilities.length, 'capability', 'capabilities')} in ${plural(o.layers.length, 'layer', 'layers')}, from ${Math.max(...sizes)} in ${list(big)} to ${Math.min(...sizes)} in ${list(small)}, each shown with its cognitive mapping.`;
}

// --------------------------------------------------- F-S4 edge types

export function edgeTypesCaption(o: Ontology = loadOntology()): string {
  return `Each of the ${plural(o.edgeTypes.length, 'edge type', 'edge types')} with the first edge of that type in the ontology, whether it is transitive or symmetric, and how many the ontology has.`;
}

// ------------------------------------------------ §4.4 safety-critical panels

/** Capabilities whose ontology entry sets requires_checkpoint or requires_approval, in table order. */
export function safetyCritical(o: Ontology = loadOntology()): Capability[] {
  const order = o.layers.flatMap((l) => l.capabilities);
  return order.map((id) => o.byId.get(id)!).filter((c) => c.requires_checkpoint || c.requires_approval);
}

export function safetyCriticalCaption(o: Ontology = loadOntology()): string {
  const caps = safetyCritical(o);
  return `In the ontology, ${plural(caps.length, 'capability needs', 'capabilities need')} a checkpoint or approval before each use: ${list(caps.map((c) => c.id))}.`;
}

// ------------------------------------------------------ F-S5 step anatomy

/**
 * The five groups of a step's fields (visual spec 3.9, F-S5). Every property
 * of `$defs/step` must be in exactly one group, and every name here must be
 * a property, or stepAnatomy() throws.
 */
export const STEP_GROUPS: readonly { id: string; title: string; slots: readonly string[] }[] = [
  { id: 'identity', title: 'Identity', slots: ['capability', 'purpose', 'domain', 'store_as', 'output_conforms_to'] },
  { id: 'wiring', title: 'Wiring', slots: ['input_bindings', 'mapping_ref', 'workflow_id', 'parallel_group', 'join'] },
  { id: 'control', title: 'Control', slots: ['condition', 'skip_if_false', 'gates', 'failure_modes', 'timeout', 'retry', 'handler'] },
  { id: 'waiting', title: 'Waiting and people', slots: ['wait', 'delay', 'approval', 'after_deferral', 'quorum'] },
  { id: 'safety', title: 'Safety', slots: ['risk', 'mutation', 'requires_checkpoint', 'requires_approval'] },
];

export function stepAnatomy(schema: CatalogSchema = loadCatalogSchema()): { id: string; title: string; slots: SchemaSlot[] }[] {
  const byName = new Map(schema.stepSlots.map((s) => [s.name, s]));
  const grouped = STEP_GROUPS.flatMap((g) => g.slots);
  const problems = [
    ...schema.stepSlots.filter((s) => !grouped.includes(s.name)).map((s) => `schema step property ${s.name} is in no group`),
    ...grouped.filter((n) => !byName.has(n)).map((n) => `group slot ${n} is not a schema step property`),
    ...grouped.filter((n, i) => grouped.indexOf(n) !== i).map((n) => `group slot ${n} is listed twice`),
  ];
  if (problems.length > 0) throw new Error(`spec figures: step anatomy: ${problems.join('; ')}`);
  return STEP_GROUPS.map((g) => ({ id: g.id, title: g.title, slots: g.slots.map((n) => byName.get(n)!) }));
}

/** For each field named in a §5.2 table row, the first field of that row (the row's id in the page). */
export function stepFieldRows(text: string, where: string): Map<string, string> {
  const out = new Map<string, string>();
  const tables = sectionBlocks(text, '5.2 ', where).filter((n): n is Table => n.type === 'table');
  for (const t of tables.filter((x) => tableRows(x)[0]?.[0] === 'Field')) {
    for (const codes of tableCodes(t).slice(1).map((r) => r[0] ?? [])) {
      for (const c of codes) if (!out.has(c)) out.set(c, codes[0]!);
    }
  }
  return out;
}

export function stepAnatomyCaption(schema: CatalogSchema = loadCatalogSchema()): string {
  const groups = stepAnatomy(schema);
  const all = groups.flatMap((g) => g.slots);
  const req = all.filter((s) => s.required).map((s) => s.name);
  return `A step has ${plural(all.length, 'field', 'fields')} in ${plural(groups.length, 'group', 'groups')}; ${plural(req.length, 'is', 'are')} required (${list(req)}), and the rest are optional.`;
}

// ------------------------------------------ F-S7 anatomy of a reference

export interface ReferenceSegment {
  kind: 'field' | 'index' | 'slice';
  text: string;
}

export interface ReferenceParts {
  root: string;
  segments: ReferenceSegment[];
  annotation: string | null;
}

const IDENT = /^[A-Za-z_][A-Za-z0-9_-]*/;

/**
 * A `${...}` reference split as §5.3 defines it: the root, then field,
 * index and slice segments, then an optional `: type` annotation. Throws on
 * anything else. Its root agrees with referenceRoots().
 */
export function referenceParts(ref: string): ReferenceParts {
  const m = /^\$\{([\s\S]*)\}$/.exec(ref.trim());
  if (!m) throw new Error(`spec figures: "${ref}" is not a \${...} reference`);
  let rest = m[1]!;
  const root = IDENT.exec(rest)?.[0];
  if (!root) throw new Error(`spec figures: "${ref}" has no root`);
  rest = rest.slice(root.length);
  const segments: ReferenceSegment[] = [];
  for (;;) {
    const field = /^\.([A-Za-z_][A-Za-z0-9_-]*)/.exec(rest);
    const index = /^\[(0|[1-9][0-9]*)\]/.exec(rest);
    const slice = /^\[((?:0|[1-9][0-9]*)?:(?:0|[1-9][0-9]*)?)\]/.exec(rest);
    const hit = field ?? index ?? slice;
    if (!hit) break;
    segments.push({ kind: field ? 'field' : index ? 'index' : 'slice', text: hit[0] });
    rest = rest.slice(hit[0].length);
  }
  const ann = /^\s*:\s*(\S[\s\S]*?)\s*$/.exec(rest);
  if (rest.trim() !== '' && !ann) throw new Error(`spec figures: "${ref}" has "${rest}" after its path`);
  const roots = [...referenceRoots(ref)];
  if (roots.length !== 1 || roots[0] !== root) throw new Error(`spec figures: "${ref}" root ${root} disagrees with referenceRoots (${roots.join(', ')})`);
  return { root, segments, annotation: ann ? ann[1]! : null };
}

/** The lines of §5.3's "Examples" fence, each split into parts. */
export function bindingExamples(text: string, where: string): { line: string; parts: ReferenceParts }[] {
  const fence = sectionFence(text, '5.3 ', 1, where);
  return fence.value
    .split('\n')
    .filter((l) => l.trim() !== '')
    .map((line) => ({ line: line.trim(), parts: referenceParts(line) }));
}

/** §5.3's bullet that says what a root can be (it starts "`root` is"). */
export function rootRule(text: string, where: string): string {
  const items = sectionBlocks(text, '5.3 ', where)
    .filter((n): n is List => n.type === 'list')
    .flatMap((l) => l.children as ListItem[])
    .map((i) => toString(i).replace(/\s+/g, ' ').trim());
  const hit = items.find((i) => i.startsWith('root is '));
  if (!hit) throw new Error(`${where}: §5.3 has no bullet starting "\`root\` is"`);
  return hit;
}

export function referenceCaption(examples: { parts: ReferenceParts }[]): string {
  const seg = examples.flatMap((e) => e.parts.segments);
  const kinds = [...new Set(seg.map((s) => s.kind))];
  const typed = examples.filter((e) => e.parts.annotation).length;
  return `The ${plural(examples.length, 'example', 'examples')} of §5.3 split into a root, ${plural(seg.length, 'path segment', 'path segments')} (${list(kinds.map((k) => `${k}`))}) and ${plural(typed, 'type annotation', 'type annotations')}.`;
}

// --------------------------------------------- F-S8 annotation types

export interface AnnotationGroup {
  /** The typeGlyphs() family key, or null for null and the wrappers. */
  family: string | null;
  names: string[];
}

/** The type names of §5.3's "Annotation grammar" sentence and its subtype statement. */
export function annotationGrammar(text: string, where: string): { names: string[]; subtype: { sub: string; of: string } | null } {
  const para = sectionBlocks(text, '5.3 ', where)
    .filter((n) => n.type === 'paragraph')
    .map((n) => {
      const codes: string[] = [];
      const walk = (x: { type: string; value?: string; children?: unknown[] }) => {
        if (x.type === 'inlineCode') codes.push(x.value!);
        for (const c of (x.children ?? []) as (typeof x)[]) walk(c);
      };
      walk(n as never);
      return { text: toString(n), codes };
    })
    .find((p) => p.text.startsWith('Annotation grammar:'));
  if (!para) throw new Error(`${where}: §5.3 has no "**Annotation grammar:**" paragraph`);
  const sub = /`?(\w+)`? is a subtype of `?(\w+)`?/.exec(para.text);
  // The grammar's names are the code spans before the subtype sentence.
  const cut = sub ? para.codes.indexOf(sub[1]!, para.codes.indexOf(sub[1]!) + 1) : -1;
  const names = cut === -1 ? para.codes : para.codes.slice(0, cut);
  return { names: names.filter((n) => /^[a-z]/.test(n) && !/^\$\{/.test(n)), subtype: sub ? { sub: sub[1]!, of: sub[2]! } : null };
}

/** The family a grammar name falls in: its typeGlyphs() family with placeholders read as open, or null. */
function familyOf(name: string): string | null {
  if (/^(nullable|union)</.test(name) || name === 'null') return null;
  const g = typeGlyphs(name.replace(/\b[TKV]\b|…/g, 'any'));
  return g[0] ?? '';
}

export function annotationGroups(names: string[]): AnnotationGroup[] {
  const problems = names.filter((n) => familyOf(n) === '');
  if (problems.length > 0) throw new Error(`spec figures: annotation types with no type glyph: ${problems.join(', ')}`);
  const out: AnnotationGroup[] = [];
  for (const n of names) {
    const f = familyOf(n);
    const g = out.find((x) => x.family === f);
    if (g) g.names.push(n);
    else out.push({ family: f, names: [n] });
  }
  return out;
}

/** A container name split around its slot: "array<T>" -> { open: "array<", slot: "T", close: ">" }. */
export function containerParts(name: string): { open: string; slot: string; close: string } | null {
  const m = /^([a-z]+<)(.+)(>)$/.exec(name);
  return m ? { open: m[1]!, slot: m[2]!, close: m[3]! } : null;
}

export function annotationCaption(names: string[], groups: AnnotationGroup[]): string {
  const containers = names.filter((n) => containerParts(n));
  return `The annotation grammar names ${plural(names.length, 'type', 'types')} in ${plural(groups.length, 'group', 'groups')}; ${plural(containers.length, 'is a container', 'are containers')} with a slot for another type.`;
}

// ------------------------------------------ F-S9 gates, F-S10 failures

export function gateBranches(schema: CatalogSchema = loadCatalogSchema()): { phase: string; actions: string[] }[] {
  return schema.gatePhases.map((phase) => ({
    phase,
    actions: phase === 'after' ? schema.gateActions.filter((a) => !schema.afterGateForbidden.includes(a)) : schema.gateActions,
  }));
}

export function gateCaption(schema: CatalogSchema = loadCatalogSchema()): string {
  const b = gateBranches(schema);
  const parts = b.map((x) => `${x.phase} the step it can take ${plural(x.actions.length, 'action', 'actions')}`);
  const lost = schema.afterGateForbidden;
  return `A gate's \`when\` decides; ${parts.join(', and ')}${lost.length > 0 ? `, since an after-gate cannot ${list(lost)}` : ''}.`.replace(/`/g, '');
}

/**
 * Each failure-mode action with its effect before recovery, from the §5.12
 * "Effect before recovery" table. An enum value with no row, or a row naming
 * a value the enum does not have, throws.
 */
export function failureBranches(text: string, where: string, schema: CatalogSchema = loadCatalogSchema()): { action: string; effect: string }[] {
  const t = sectionTableByHeader(text, '5.12 ', 'action', where);
  const codes = tableCodes(t).slice(1);
  const rows = tableRows(t).slice(1);
  const effect = new Map<string, string>();
  rows.forEach((r, i) => {
    for (const a of codes[i]![0] ?? []) effect.set(a, r[1]!);
  });
  const problems = [
    ...schema.failureActions.filter((a) => !effect.has(a)).map((a) => `action ${a} has no row`),
    ...[...effect.keys()].filter((a) => !schema.failureActions.includes(a)).map((a) => `row names ${a}, which is not a failure action`),
  ];
  if (problems.length > 0) throw new Error(`${where}: §5.12 "Effect before recovery" table: ${problems.join('; ')}`);
  return schema.failureActions.map((action) => ({ action, effect: effect.get(action)! }));
}

export function failureCaption(branches: { action: string; effect: string }[]): string {
  const none = branches.filter((b) => /^None\b/.test(b.effect)).map((b) => b.action);
  return `A fired failure mode takes one of ${plural(branches.length, 'action', 'actions')}; ${list(none)} change nothing before recovery, and the others act first.`;
}
