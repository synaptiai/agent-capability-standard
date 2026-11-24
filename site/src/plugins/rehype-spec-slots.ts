// Figure slots in the current Standard (visual spec 3.9, "Placement by
// block"): for each entry of SPEC_SLOTS, an empty marker element is put
// under its heading, after or before its block (after one item of a list,
// split there), or on both sides of a block the figure wraps. SpecPage cuts the rendered HTML at the markers and draws
// the figures there. A slot whose section or block is missing, or whose
// block no longer starts with the text the map records, fails the build.
//
// It also turns the diagnostic codes in the Code column of the tables the
// figures enrich (§5.8.3, and the §9.2 to §9.7 code tables) into diagnostic
// tiles: the code, a severity glyph and a solid (error) or dashed (warning)
// border, linked to the code's row on the diagnostics page. A code the
// diagnostics loader does not know fails the build.
import type { Element, ElementContent, Root, RootContent } from 'hast';
import type { VFile } from 'vfile';
import { loadDiagnostics, type Diagnostic } from '../data/diagnostics';
import { diagnosticHref } from '../lib/generated';
import { SPEC_SLOTS, type SlotBlock, type SlotItem, type SpecSlot } from '../lib/spec-slots';
import { CODE_TABLE_FIGURES } from '../lib/spec-tail-figures';
import { glyphElement } from '../pixel/hast';
import { failWith, sourceOf } from './source';
import { hastText, isEl } from './hast';

export interface RehypeSpecSlotsOptions {
  /** Repo path of the current Standard (diagnostic tiles). */
  current: string;
  /** The slot map of each Standard file that has figures, by repo path. */
  slots: ReadonlyMap<string, readonly SpecSlot[]>;
}

const PLUGIN = 'rehype-spec-slots';

const isHeading = (n: Element) => /^h[1-6]$/.test(n.tagName);
const squash = (s: string) => s.replace(/\s+/g, ' ').trim();

const TAG: Record<SlotBlock, (e: Element) => boolean> = {
  table: (e) => e.tagName === 'table',
  code: (e) => e.tagName === 'pre',
  list: (e) => e.tagName === 'ul' || e.tagName === 'ol',
  paragraph: (e) => e.tagName === 'p',
};

/** The text a slot's `startsWith` is compared with: a table's header cells, a fence's first line, a list's first item, a paragraph. */
export function blockText(e: Element, kind: SlotBlock): string {
  if (kind === 'table') {
    const head = e.children.find((c): c is Element => isEl(c, 'thead'));
    const tr = head?.children.find((c): c is Element => isEl(c, 'tr'));
    return squash((tr?.children ?? []).filter((c): c is Element => isEl(c)).map((c) => hastText(c)).join(' '));
  }
  if (kind === 'code') return squash(hastText(e).replace(/^\n+/, '').split('\n')[0] ?? '');
  if (kind === 'list') return squash(hastText(e.children.find((c): c is Element => isEl(c, 'li')) ?? e));
  return squash(hastText(e));
}

const marker = (key: string, at: 'here' | 'start' | 'end'): Element => ({
  type: 'element',
  tagName: 'div',
  properties: { dataFigSlot: key, dataFigAt: at },
  children: [],
});

/** Root children from the slot's heading to the end of its section, or null. */
function section(kids: RootContent[], slot: SpecSlot): { head: number; els: { el: Element; i: number }[] } | null {
  const heads = kids.flatMap((n, i) => (isEl(n) && n.tagName === `h${slot.level}` && squash(hastText(n)).startsWith(slot.section) ? [i] : []));
  if (heads.length !== 1) return null;
  const head = heads[0]!;
  const els: { el: Element; i: number }[] = [];
  for (let i = head + 1; i < kids.length; i++) {
    const n = kids[i]!;
    if (!isEl(n)) continue;
    if (isHeading(n) && Number(n.tagName[1]) <= slot.level) break;
    els.push({ el: n, i });
  }
  return { head, els };
}

/**
 * Cuts a list directly after `item`, which must start with its recorded words
 * and not be the last item: the items after it move to a new list, returned,
 * which an ordered list's `start` keeps numbering on. A problem otherwise.
 */
function splitList(list: Element, item: SlotItem, where: string): Element | string {
  const items = list.children.filter((c): c is Element => isEl(c, 'li'));
  const hit = items[item.index];
  if (!hit || item.index === items.length - 1) return `${where} has ${items.length} item(s), none after item ${item.index + 1}`;
  const text = squash(hastText(hit));
  if (!text.startsWith(item.startsWith)) return `item ${item.index + 1} of ${where} starts "${text.slice(0, 40)}", not "${item.startsWith}"`;
  const rest = list.children.splice(list.children.indexOf(hit) + 1);
  const properties = { ...list.properties };
  if (list.tagName === 'ol') properties.start = Number(list.properties.start ?? 1) + item.index + 1;
  return { ...list, properties, children: rest };
}

/** Puts every slot's markers in the tree. Returns the problems found. */
export function placeSlots(tree: Root, slots: readonly SpecSlot[] = SPEC_SLOTS): string[] {
  const problems: string[] = [];
  const inserts: { i: number; nodes: Element[] }[] = [];
  for (const slot of slots) {
    const sec = section(tree.children, slot);
    if (!sec) {
      problems.push(`slot ${slot.key}: expected one h${slot.level} starting "${slot.section}"`);
      continue;
    }
    if (slot.at === 'heading') {
      inserts.push({ i: sec.head + 1, nodes: [marker(slot.key, 'here')] });
      continue;
    }
    const { place, block, index, startsWith } = slot.at;
    const blocks = sec.els.filter((x) => TAG[block](x.el));
    const hit = blocks[index];
    if (!hit) {
      problems.push(`slot ${slot.key}: §${slot.section.trim()} has ${blocks.length} ${block} block(s), no block ${index + 1}`);
      continue;
    }
    const text = blockText(hit.el, block);
    if (!text.startsWith(startsWith)) {
      problems.push(`slot ${slot.key}: ${block} ${index + 1} of §${slot.section.trim()} starts "${text.slice(0, 40)}", not "${startsWith}"`);
      continue;
    }
    if (slot.at.item) {
      const where = `list ${index + 1} of §${slot.section.trim()}`;
      const rest = place === 'after' && block === 'list' ? splitList(hit.el, slot.at.item, where) : 'an item is placed after, in a list';
      if (typeof rest === 'string') problems.push(`slot ${slot.key}: ${rest}`);
      else inserts.push({ i: hit.i + 1, nodes: [marker(slot.key, 'here'), rest] });
    } else if (place === 'before') inserts.push({ i: hit.i, nodes: [marker(slot.key, 'here')] });
    else if (place === 'after') inserts.push({ i: hit.i + 1, nodes: [marker(slot.key, 'here')] });
    else {
      inserts.push({ i: hit.i, nodes: [marker(slot.key, 'start')] });
      inserts.push({ i: hit.i + 1, nodes: [marker(slot.key, 'end')] });
    }
  }
  // Insert from the end so earlier indices stay valid; equal indices keep map order.
  inserts
    .map((x, order) => ({ ...x, order }))
    .sort((a, b) => b.i - a.i || b.order - a.order)
    .forEach((x) => tree.children.splice(x.i, 0, ...x.nodes));
  return problems;
}

/** A diagnostic code as a tile linked to its row on the diagnostics page (hast form of the page's DiagnosticTile). */
export function diagnosticTileElement(d: Diagnostic): Element {
  return {
    type: 'element',
    tagName: 'a',
    properties: { className: ['diag-tile', `diag-tile--${d.severity}`], href: diagnosticHref(d.code), dataCode: d.code },
    children: [
      { type: 'element', tagName: 'code', properties: { className: ['diag-tile__code'] }, children: [{ type: 'text', value: d.code }] },
      glyphElement(`severity:${d.severity}`, { className: 'diag-tile__severity' }),
      { type: 'element', tagName: 'span', properties: { className: ['visually-hidden'] }, children: [{ type: 'text', value: `, ${d.severity}` }] },
    ],
  };
}

const CODE = /^[A-Z]\d{3}$/;

/** Turns each diagnostic code in a table's column headed `column` into a tile. */
export function diagnosticTiles(table: Element, byCode: Map<string, Diagnostic>, problems: string[], where: string, column = 'Code'): number {
  const rows = (part: string) =>
    (table.children.find((c): c is Element => isEl(c, part))?.children ?? []).filter((c): c is Element => isEl(c, 'tr'));
  const head = rows('thead')[0];
  const cells = (tr: Element) => tr.children.filter((c): c is Element => isEl(c, 'td') || isEl(c, 'th'));
  const col = head ? cells(head).findIndex((c) => squash(hastText(c)) === column) : -1;
  if (col === -1) {
    problems.push(`${where}: no "${column}" column`);
    return 0;
  }
  let n = 0;
  for (const tr of rows('tbody')) {
    const cell = cells(tr)[col];
    if (!cell) continue;
    const tile = (code: string): ElementContent | null => {
      const d = byCode.get(code);
      if (!d) {
        problems.push(`${where}: ${code} is not a diagnostic code of the Standard`);
        return null;
      }
      n++;
      return diagnosticTileElement(d);
    };
    cell.children = cell.children.flatMap((c): ElementContent[] => {
      if (isEl(c, 'code')) {
        const code = hastText(c).trim();
        return [(CODE.test(code) && tile(code)) || c];
      }
      if (c.type !== 'text') return [c];
      // Plain-text codes ("B202 / B201"): each code a tile, the words between kept.
      return c.value.split(/\b([A-Z]\d{3})\b/).flatMap((part, i): ElementContent[] => {
        if (i % 2 === 0) return part === '' ? [] : [{ type: 'text', value: part }];
        return [tile(part) ?? { type: 'text', value: part }];
      });
    });
    if (column === 'Code') cell.properties = { ...cell.properties, className: ['diag-cell'] };
  }
  return n;
}

/** The tables whose codes become tiles: the Code column of §5.8.3 and §9.2 to §9.7, the codes in §5.16's field descriptions and in §5.19.1's responses. */
const TILE_SECTIONS: readonly { level: number; section: string; column?: string; index?: number }[] = [
  { level: 4, section: '5.8.3 ' },
  { level: 3, section: '5.16 ', column: 'Description' },
  { level: 4, section: '5.19.1 ', column: 'Responses' },
  ...['9.2 ', '9.3 ', '9.4 ', '9.5 ', '9.6 ', '9.7 '].map((section) => ({ level: 3, section })),
  // The code tables of §5.18 and the other sections (CODE_TABLE_FIGURES).
  ...Object.values(CODE_TABLE_FIGURES).map(({ level, section, index }) => ({ level, section, index: index ?? 0 })),
];

export default function rehypeSpecSlots(options: RehypeSpecSlotsOptions) {
  return (tree: Root, file: VFile): void => {
    const { repoPath } = sourceOf(file, PLUGIN);
    const slots = options.slots.get(repoPath);
    if (!slots) return;
    const problems: string[] = [];
    if (repoPath !== options.current) {
      failWith(PLUGIN, placeSlots(tree, slots).map((p) => `${repoPath}: ${p}`));
      return;
    }
    const byCode = new Map(loadDiagnostics().map((d) => [d.code, d]));
    for (const s of TILE_SECTIONS) {
      const sec = section(tree.children, { key: '', level: s.level, section: s.section, at: 'heading' });
      const table = sec?.els.filter((x) => x.el.tagName === 'table')[s.index ?? 0];
      if (!table) {
        problems.push(`§${s.section.trim()} has no table for diagnostic tiles`);
        continue;
      }
      if (diagnosticTiles(table.el, byCode, problems, `§${s.section.trim()}`, s.column) === 0) problems.push(`§${s.section.trim()}: no diagnostic code to draw as a tile`);
    }
    problems.push(...placeSlots(tree, slots));
    failWith(PLUGIN, problems.map((p) => `${repoPath}: ${p}`));
  };
}
