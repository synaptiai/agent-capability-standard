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
//   Standard fail the build instead of silently moving a figure;
// - `wrap`: around that block, which becomes the figure's drawing (a source
//   table enriched in place, such as the §5.8.3 codes as diagnostic tiles).
// Block kinds: `table`, `code` (a fenced block), `list`, `paragraph`.
// Slots are listed in page order; the page numbers its figures in that order.

export type SlotBlock = 'table' | 'code' | 'list' | 'paragraph';

export interface SpecSlot {
  key: string;
  level: number;
  section: string;
  at: 'heading' | { place: 'after' | 'before' | 'wrap'; block: SlotBlock; index: number; startsWith: string };
}

const after = (block: SlotBlock, index: number, startsWith: string) => ({ place: 'after' as const, block, index, startsWith });

export const SPEC_SLOTS: readonly SpecSlot[] = [
  { key: 'requirements', level: 3, section: '1.2 ', at: after('list', 0, 'MUST, MUST NOT, SHALL, SHALL NOT: Absolu') },
  { key: 'safety-order', level: 3, section: '3.3 ', at: after('list', 0, 'A checkpoint MUST run before every mutat') },
  { key: 'fields', level: 3, section: '4.1 ', at: 'heading' },
  { key: 'layers', level: 3, section: '4.2 ', at: 'heading' },
  { key: 'edges', level: 3, section: '4.3 ', at: 'heading' },
  { key: 'safety', level: 3, section: '4.4 ', at: 'heading' },
  { key: 'step', level: 3, section: '5.2 ', at: 'heading' },
  { key: 'safety-defaults', level: 4, section: '5.2.1 ', at: 'heading' },
  { key: 'reference', level: 3, section: '5.3 ', at: 'heading' },
  { key: 'annotations', level: 3, section: '5.4 ', at: 'heading' },
  { key: 'gates', level: 3, section: '5.6 ', at: 'heading' },
  { key: 'failures', level: 3, section: '5.7 ', at: 'heading' },
  { key: 'precedence', level: 4, section: '5.8.1 ', at: after('code', 0, 'expr = or_expr ;') },
  { key: 'static-checks', level: 4, section: '5.8.3 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'Check Code' } },
  { key: 'extensions', level: 3, section: '5.9 ', at: after('table', 0, 'Extension Fields it governs') },
  { key: 'triggers', level: 3, section: '5.10 ', at: after('table', 0, 'Field Description') },
  { key: 'recovery-loop', level: 3, section: '5.12 ', at: 'heading' },
  { key: 'recovery-replay', level: 3, section: '5.12 ', at: after('table', 1, 'Recovery Outcome') },
  { key: 'wait-timeline', level: 3, section: '5.13 ', at: after('code', 0, '- capability: receive') },
  { key: 'silent-source', level: 3, section: '5.13 ', at: after('code', 1, 'failure_modes:') },
  { key: 'wait-replay', level: 3, section: '5.13 ', at: { place: 'before', block: 'paragraph', index: 5, startsWith: 'Delays. A step may declare delay, a dura' } },
  { key: 'approval', level: 3, section: '5.14 ', at: after('table', 0, 'Field Description') },
  { key: 'deferral-replay', level: 3, section: '5.14 ', at: after('list', 0, 'fail (default) → F502.') },
  { key: 'delegate', level: 3, section: '5.15 ', at: after('code', 0, '- capability: delegate') },
  { key: 'quorum', level: 3, section: '5.16 ', at: after('code', 0, '- capability: constrain') },
  { key: 'quorum-fields', level: 3, section: '5.16 ', at: { place: 'wrap', block: 'table', index: 0, startsWith: 'Field Description' } },
  { key: 'trust-classes', level: 3, section: '5.17 ', at: after('code', 0, '- capability: receive') },
  { key: 'sender-filter', level: 3, section: '5.17 ', at: after('table', 0, 'Input Effect on an item') },
];

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
