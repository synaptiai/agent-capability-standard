// Where each site-drawn figure of the current Standard goes (visual spec
// 3.9, "Placement by block, not only by heading"). Data only, with no
// imports, so the check scripts can read it with plain `node`.
//
// A slot names its section by heading level and the start of the heading
// text ("5.13 " finds "5.13 Waiting for Events"; a section ends at the next
// heading of the same or a higher level, so an h3 section takes in its h4s).
// It is then placed:
// - `heading`: directly under the heading;
// - `after` or `before` a block: the k-th (0-based) block of that kind in the
//   section, whose text starts with `startsWith` (the first 40 characters of
//   its first line, whitespace collapsed). The check makes an edit to the
//   Standard fail the build instead of silently moving a figure. `after` a
//   list may name one of its items (`item`, 0-based, with the start of its
//   text): the figure then goes directly after that item, the list split
//   there and the items after it continuing its numbering;
// - `wrap`: around that block, which becomes the figure's drawing (a source
//   table enriched in place, such as the §5.8.3 codes as diagnostic tiles).
// Block kinds: `table`, `code` (a fenced block), `list`, `paragraph`.
// Slots are listed in page order; the page numbers its figures in that order.

export type SlotBlock = 'table' | 'code' | 'list' | 'paragraph';

export interface SpecSlot {
  key: string;
  level: number;
  section: string;
  at: 'heading' | { place: 'after' | 'before' | 'wrap'; block: SlotBlock; index: number; startsWith: string; item?: SlotItem };
}

/** An item of a list, by its place in the list (0-based) and the start of its text, whitespace collapsed. */
export interface SlotItem {
  index: number;
  startsWith: string;
}

const after = (block: SlotBlock, index: number, startsWith: string) => ({ place: 'after' as const, block, index, startsWith });
// Directly after one item of a list, which is split there (a figure that shows that item).
const afterItem = (index: number, startsWith: string, item: SlotItem) => ({ place: 'after' as const, block: 'list' as const, index, startsWith, item });
// A field table drawn as a Port column, the table folded under it (TABLE_FIGURES in spec-tail-figures).
const fieldTable = (index = 0) => ({ place: 'wrap' as const, block: 'table' as const, index, startsWith: 'Field Type Required Description' });
// A table whose Code column is drawn as diagnostic tiles (CODE_TABLE_FIGURES in spec-tail-figures);
// `index` is the table's place among the section's tables.
const codeTable = (startsWith: string, index = 0) => ({ place: 'wrap' as const, block: 'table' as const, index, startsWith });

export const SPEC_SLOTS: readonly SpecSlot[] = [
  { key: 'requirements', level: 3, section: '1.2 ', at: after('list', 0, 'MUST, MUST NOT, SHALL, SHALL NOT: Absolu') },
  { key: 'host-loop', level: 2, section: '2. ', at: after('table', 0, 'Term Definition') },
  { key: 'principles', level: 2, section: '3. ', at: 'heading' },
  { key: 'safety-order', level: 3, section: '3.3 ', at: after('list', 0, 'A checkpoint MUST run before every mutat') },
  { key: 'table-4.1', level: 3, section: '4.1 ', at: fieldTable() },
  { key: 'dialect-forms', level: 4, section: '4.1.2 ', at: codeTable('Form Meaning Rendering Code') },
  { key: 'layers', level: 3, section: '4.2 ', at: 'heading' },
  { key: 'edges', level: 3, section: '4.3 ', at: 'heading' },
  { key: 'safety', level: 3, section: '4.4 ', at: 'heading' },
  { key: 'rollback-replay', level: 4, section: '4.4.1 ', at: after('table', 0, 'Field Meaning') },
  { key: 'not-covered-replay', level: 4, section: '4.4.1 ', at: after('paragraph', 4, 'At run time. A rollback step completes w') },
  { key: 'send-key-replay', level: 4, section: '4.4.2 ', at: after('paragraph', 2, 'A key is unique only while run_id is. A ') },
  { key: 'destination-replay', level: 4, section: '4.4.2 ', at: after('paragraph', 7, 'The policies in force for a run are thos') },
  { key: 'scope-replay', level: 3, section: '4.5 ', at: after('paragraph', 3, 'A host that does not provide the scope as') },
  { key: 'stored-replay', level: 3, section: '4.5 ', at: after('paragraph', 4, 'stored: true asserts that the data is st') },
  { key: 'table-5.1', level: 3, section: '5.1 ', at: fieldTable() },
  { key: 'export-replay', level: 4, section: '5.1.1 ', at: after('code', 0, '# Standard version: 1.2.0') },
  { key: 'step', level: 3, section: '5.2 ', at: 'heading' },
  { key: 'safety-defaults', level: 4, section: '5.2.1 ', at: 'heading' },
  { key: 'group-replay', level: 4, section: '5.2.3 ', at: after('paragraph', 1, 'A group is complete when every member ha') },
  { key: 'reference', level: 3, section: '5.3 ', at: 'heading' },
  { key: 'annotations', level: 3, section: '5.4 ', at: 'heading' },
  { key: 'gates', level: 3, section: '5.6 ', at: 'heading' },
  { key: 'failures', level: 3, section: '5.7 ', at: 'heading' },
  { key: 'precedence', level: 4, section: '5.8.1 ', at: after('code', 0, 'expr = or_expr ;') },
  { key: 'static-checks', level: 4, section: '5.8.3 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'Check Code' } },
  { key: 'extensions', level: 3, section: '5.9 ', at: after('table', 0, 'Extension Fields it governs') },
  { key: 'triggers', level: 3, section: '5.10 ', at: after('table', 0, 'Field Description') },
  { key: 'overlap', level: 4, section: '5.10.2 ', at: after('list', 1, 'skip (default): no run starts for that f') },
  { key: 'recovery-loop', level: 3, section: '5.12 ', at: 'heading' },
  { key: 'recovery-replay', level: 3, section: '5.12 ', at: after('table', 1, 'Recovery Outcome') },
  { key: 'wait-timeline', level: 3, section: '5.13 ', at: after('code', 0, '- capability: receive') },
  { key: 'silent-source', level: 3, section: '5.13 ', at: after('code', 1, 'failure_modes:') },
  { key: 'wait-replay', level: 3, section: '5.13 ', at: { place: 'before', block: 'paragraph', index: 7, startsWith: 'Delays. A step may declare delay, a dura' } },
  { key: 'approval', level: 3, section: '5.14 ', at: after('table', 0, 'Field Description') },
  { key: 'approval-unattended-replay', level: 3, section: '5.14 ', at: after('paragraph', 4, 'The mode changes neither the shown value') },
  { key: 'recheck-replay', level: 3, section: '5.14 ', at: after('list', 3, 'reask (default): the step is asked again') },
  { key: 'deferral-replay', level: 3, section: '5.14 ', at: after('list', 4, 'fail (default) → F502.') },
  { key: 'resume-replay', level: 4, section: '5.14.1 ', at: after('paragraph', 0, 'A run that ended with outcome deferred c') },
  { key: 'resume-skip-replay', level: 4, section: '5.14.1 ', at: afterItem(0, 'What it keeps. Its stores, inputs, injec', { index: 5, startsWith: 'The record. A re-entered step continues' }) },
  { key: 'delegate', level: 3, section: '5.15 ', at: after('code', 0, '- capability: delegate') },
  { key: 'family-replay', level: 3, section: '5.15 ', at: after('list', 0, 'keep the part of the identifier after it') },
  { key: 'manifest-replay', level: 4, section: '5.15.1 ', at: after('table', 0, 'Field Required Description') },
  { key: 'agents-replay', level: 4, section: '5.15.2 ', at: after('list', 0, 'Only listed agents. A literal agent that') },
  { key: 'read-only-replay', level: 4, section: '5.15.2 ', at: after('paragraph', 4, 'Read-only. A host that receives a delega') },
  { key: 'continue-replay', level: 4, section: '5.15.3 ', at: after('list', 0, 'a step that binds continues and a litera') },
  { key: 'delegate-rollback-replay', level: 4, section: '5.15.4 ', at: after('list', 0, 'Authorisation. A run\'s checkpoints autho') },
  { key: 'quorum', level: 3, section: '5.16 ', at: after('code', 0, '- capability: constrain') },
  { key: 'quorum-fields', level: 3, section: '5.16 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'Field Description' } },
  { key: 'trust-classes', level: 3, section: '5.17 ', at: after('code', 0, '- capability: receive') },
  { key: 'sender-filter', level: 3, section: '5.17 ', at: after('table', 0, 'Input Effect on an item') },
  { key: 'approver-count', level: 3, section: '5.17 ', at: after('list', 0, 'for a human approver, including one aske') },
  { key: 'table-5.18.1', level: 4, section: '5.18.1 ', at: fieldTable() },
  { key: 'offered-tools', level: 4, section: '5.18.2 ', at: codeTable('Offered tool or host action Code') },
  { key: 'classification', level: 4, section: '5.18.3 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'What the call does Capability' } },
  { key: 'shell-like-calls', level: 4, section: '5.18.3 ', at: after('list', 0, 'a source is one the layer can neither re') },
  { key: 'os-boundary', level: 4, section: '5.18.3 ', at: { place: 'wrap', block: 'table', index: 1, startsWith: 'Property What holds' } },
  { key: 'composite-codes', level: 4, section: '5.18.4 ', at: codeTable('Composite Code') },
  { key: 'edge-codes', level: 4, section: '5.18.5 ', at: codeTable('Edge Over calls Code') },
  { key: 'checkpoint-refusals', level: 4, section: '5.18.6 ', at: codeTable('Call Refused without Code') },
  { key: 'call-refusals', level: 4, section: '5.18.8 ', at: codeTable('Code The call is refused because') },
  { key: 'capability-checks', level: 4, section: '5.18.10 ', at: codeTable('Capability Check Code') },
  { key: 'protocol-actions', level: 4, section: '5.19.1 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'Action The host Responses' } },
  { key: 'protocol-replay', level: 4, section: '5.19.1 ', at: after('list', 2, "outputs: the root workflow's stores at t") },
  { key: 'response-replay', level: 4, section: '5.19.1 ', at: after('paragraph', 6, 'An Error carries its kind and a code, an') },
  { key: 'wake-replay', level: 4, section: '5.19.3 ', at: after('list', 0, 'A Sleep ends at a tick whose time is at ') },
  { key: 'cancel-replay', level: 4, section: '5.19.5 ', at: after('paragraph', 0, 'A host MAY cancel a run that has not end') },
  { key: 'reason-replay', level: 4, section: '5.19.7 ', at: after('paragraph', 0, 'An Error response MAY carry a reason, a ') },
  { key: 'run-records', level: 4, section: '5.19.8 ', at: after('paragraph', 0, 'Every run has a run record: an action re') },
  { key: 'grounding-replay', level: 3, section: '5.20 ', at: after('table', 0, 'Field Description') },
  { key: 'citation-replay', level: 3, section: '5.20 ', at: after('list', 0, 'A value that is not a list fails the ste') },
  { key: 'table-5.21.2', level: 4, section: '5.21.2 ', at: fieldTable() },
  { key: 'profile-codes', level: 4, section: '5.21.2 ', at: codeTable('Code A profile is reported when', 1) },
  { key: 'profile-raises', level: 4, section: '5.21.3 ', at: codeTable('Member Raises Code') },
  { key: 'profile-rules', level: 4, section: '5.21.3 ', at: codeTable('Member In force as Code', 1) },
  { key: 'schema-shelf', level: 3, section: '6.1 ', at: 'heading' },
  { key: 'table-6.3', level: 3, section: '6.3 ', at: fieldTable() },
  { key: 'audit-replay', level: 3, section: '6.4 ', at: { place: 'before', block: 'paragraph', index: 3, startsWith: 'The audit capability. An audit step reco' } },
  { key: 'table-6.5', level: 3, section: '6.5 ', at: fieldTable() },
  { key: 'table-6.6', level: 3, section: '6.6 ', at: fieldTable() },
  { key: 'secret-replay', level: 3, section: '6.7 ', at: after('list', 0, 'an evidence anchor, an evidence record o') },
  { key: 'table-7.1', level: 3, section: '7.1 ', at: fieldTable() },
  { key: 'merge-thresholds', level: 3, section: '7.3 ', at: 'heading' },
  { key: 'decay', level: 3, section: '8.1 ', at: after('paragraph', 2, 'Field authority is not a factor of the s') },
  { key: 'table-8.4', level: 3, section: '8.4 ', at: fieldTable() },
  { key: 'families', level: 3, section: '9.1 ', at: 'heading' },
  { key: 'codes-9.2', level: 3, section: '9.2 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'Code Name Description' } },
  { key: 'codes-9.3', level: 3, section: '9.3 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'Code Name Description' } },
  { key: 'codes-9.4', level: 3, section: '9.4 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'Code Name Description' } },
  { key: 'codes-9.5', level: 3, section: '9.5 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'Code Name Description' } },
  { key: 'code-heat', level: 3, section: '9.6 ', at: 'heading' },
  { key: 'codes-9.6', level: 3, section: '9.6 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'Code Name Description' } },
  { key: 'codes-9.7', level: 3, section: '9.7 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'Code Name Description' } },
  { key: 'levels', level: 3, section: '10.1 ', at: 'heading' },
  { key: 'suite', level: 3, section: '10.3 ', at: after('list', 0, 'Positive fixtures (valid workflows that M') },
  { key: 'digest-vectors', level: 3, section: '10.3 ', at: after('paragraph', 3, 'The approval digest vectors (tests/confo') },
  { key: 'effect-vectors', level: 3, section: '10.3 ', at: after('paragraph', 6, 'The destination vectors (tests/conforman') },
  { key: 'sl-fixtures', level: 3, section: '10.4 ', at: after('list', 1, 'A call names call (the tool), args (defa') },
  { key: 'fixture-entries', level: 3, section: '10.5 ', at: after('list', 1, '{"expect": A, "respond": R, "at": T}: th') },
  { key: 'bumps', level: 3, section: '11.4 ', at: 'heading' },
  { key: 'version-codes', level: 3, section: '11.5 ', at: codeTable('Code A workflow or catalog is reported w', 1) },
  { key: 'citing-codes', level: 3, section: '11.6 ', at: codeTable('Code A consumer reports a cited document', 1) },
  { key: 'checkpoint-tree', level: 3, section: '12.1 ', at: { place: 'wrap', block: 'code', index: 0, startsWith: 'Does the step change anything outside th' } },
  { key: 'pattern-0', level: 3, section: '12.5 ', at: { place: 'before', block: 'code', index: 0, startsWith: '- capability: plan' } },
  { key: 'pattern-1', level: 3, section: '12.5 ', at: { place: 'before', block: 'code', index: 1, startsWith: '- capability: retrieve' } },
  { key: 'pattern-2', level: 3, section: '12.5 ', at: { place: 'before', block: 'code', index: 2, startsWith: '- capability: plan' } },
  { key: 'pattern-3', level: 3, section: '12.5 ', at: { place: 'before', block: 'code', index: 3, startsWith: '- capability: constrain' } },
  { key: 'pattern-4', level: 3, section: '12.5 ', at: { place: 'before', block: 'code', index: 4, startsWith: '- capability: rollback' } },
];

/** §12.1's tree as Standards 1.0.0 and 1.1.0 write it (1.2.0 rewrote it). */
const CHECKPOINT_TREE_OLD: SpecSlot = {
  key: 'checkpoint-tree',
  level: 3,
  section: '12.1 ',
  at: { place: 'wrap', block: 'code', index: 0, startsWith: 'Does the step modify external state?' },
};

/**
 * Standard 1.0.0: only figures drawn from its own text (visual spec 3.9 gives
 * the older version chapter icons; these add what its tables, lists and
 * fences support). The ontology, schemas and fixtures are 1.1 data and are
 * not drawn here. Its §4.1 and §6.3 field tables are drawn as Port columns,
 * as on the current Standard; its other tables stay plain tables.
 */
export const SPEC_SLOTS_100: readonly SpecSlot[] = [
  { key: 'requirements', level: 3, section: '1.2 ', at: after('list', 0, 'MUST, MUST NOT, SHALL, SHALL NOT: Absolu') },
  { key: 'table-4.1', level: 3, section: '4.1 ', at: fieldTable() },
  { key: 'table-6.3', level: 3, section: '6.3 ', at: fieldTable() },
  { key: 'categories', level: 3, section: '9.1 ', at: 'heading' },
  { key: 'bumps', level: 3, section: '11.4 ', at: 'heading' },
  CHECKPOINT_TREE_OLD,
  { key: 'pattern-0', level: 3, section: '12.5 ', at: { place: 'before', block: 'code', index: 0, startsWith: '- capability: plan' } },
  { key: 'pattern-1', level: 3, section: '12.5 ', at: { place: 'before', block: 'code', index: 1, startsWith: '- capability: retrieve' } },
  // Its Recovery Loop fence holds one step, which a strip would not add to.
];

/**
 * Standard 1.1.0, an older version since 1.2.0: the figures of SPEC_SLOTS that
 * draw only from its own text (its tables, fences and lists), in the same
 * places, and §9.1's categories in place of the code families, as on 1.0.0.
 * The figures drawn from the ontology, the schemas, the diagnostics (§9.2 to
 * §9.7's code tables are checked against core/src/diag.rs) or the runtime
 * fixtures show current data, so they stay on the current Standard.
 */
const TEXT_FIGURES_110: ReadonlySet<string> = new Set([
  'requirements',
  'table-4.1',
  'reference',
  'annotations',
  'failures',
  'precedence',
  'static-checks',
  'triggers',
  'recovery-loop',
  'wait-timeline',
  'silent-source',
  'quorum',
  'quorum-fields',
  'sender-filter',
  'schema-shelf',
  'table-6.3',
  'levels',
  'bumps',
  'checkpoint-tree',
  'pattern-0',
  'pattern-1',
  'pattern-2',
]);
export const SPEC_SLOTS_110: readonly SpecSlot[] = SPEC_SLOTS.flatMap((s): SpecSlot[] =>
  s.key === 'families'
    ? [{ key: 'categories', level: 3, section: '9.1 ', at: 'heading' }]
    : s.key === 'checkpoint-tree'
      ? [CHECKPOINT_TREE_OLD]
      : TEXT_FIGURES_110.has(s.key)
        ? [s]
        : [],
);

/** The slot map of each Standard version that has one, by version. */
export const SLOTS_BY_VERSION: Readonly<Record<string, readonly SpecSlot[]>> = {
  '1.2.0': SPEC_SLOTS,
  '1.1.0': SPEC_SLOTS_110,
  '1.0.0': SPEC_SLOTS_100,
};

/** The marker element a slot leaves in the rendered HTML (rehype-spec-slots), and its pattern. */
export const SLOT_MARKER = /<div data-fig-slot="([^"]+)" data-fig-at="(here|start|end)"><\/div>/g;

export type SlotPiece = { html: string; key?: undefined } | { key: string; inner: string | null };

/**
 * The rendered HTML cut at its slot markers, in document order: plain HTML
 * pieces, and one piece per slot (with the wrapped block's HTML for a
 * `wrap` slot). Throws when a slot of `slots` has no marker, or a marker
 * appears twice or names no slot.
 */
export function cutAtSlots(html: string, slots: readonly SpecSlot[] = SPEC_SLOTS, where = 'spec'): SlotPiece[] {
  const out: SlotPiece[] = [];
  const seen = new Set<string>();
  const known = new Set(slots.map((s) => s.key));
  const problems: string[] = [];
  let last = 0;
  let open: { key: string; at: number } | null = null;
  for (const m of html.matchAll(new RegExp(SLOT_MARKER.source, 'g'))) {
    const [all, key, at] = m as unknown as [string, string, 'here' | 'start' | 'end'];
    if (!known.has(key)) problems.push(`marker for unknown slot ${key}`);
    if (at === 'end') {
      if (open?.key !== key) {
        problems.push(`slot ${key} ends where it did not start`);
        continue;
      }
      out.push({ key, inner: html.slice(open.at, m.index) });
      open = null;
      last = m.index! + all.length;
      continue;
    }
    if (seen.has(key)) problems.push(`slot ${key} is marked twice`);
    seen.add(key);
    out.push({ html: html.slice(last, m.index) });
    if (at === 'here') out.push({ key, inner: null });
    else open = { key, at: m.index! + all.length };
    last = m.index! + all.length;
  }
  if (open) problems.push(`slot ${open.key} starts and never ends`);
  out.push({ html: html.slice(last) });
  for (const s of slots) if (!seen.has(s.key)) problems.push(`slot ${s.key} has no marker`);
  if (problems.length > 0) throw new Error(`${where}: figure slots: ${problems.join('; ')}`);
  return out;
}
