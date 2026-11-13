// The release notes page's figures in hast (see src/lib/release-figures.ts for
// what each draws and why). Called by rehype-prose-figures for CHANGELOG.md
// before it numbers the page's figures.
import type { Element, ElementContent, Root } from 'hast';
import { loadDiagnostics } from '../data/diagnostics';
import {
  issueCounts,
  kindCount,
  kindsInUse,
  LONG_SECTION,
  parseReleases,
  sectionCaption,
  sectionCodes,
  sectionHasFigure,
  sectionTitle,
  SHOWN_ENTRIES,
  timelineCaption,
  TIMELINE_TITLE,
  type Release,
} from '../lib/release-figures';
import { pixelBarElement } from '../pixel/hast';
import { diagnosticTileElement } from './rehype-spec-slots';
import { hastText, isEl } from './hast';

/** The source whose page gets these figures. */
export const RELEASE_NOTES_SOURCE = 'CHANGELOG.md';

const el = (tagName: string, properties: Element['properties'], children: ElementContent[] = []): Element => ({
  type: 'element',
  tagName,
  properties,
  children,
});
const text = (value: string): ElementContent => ({ type: 'text', value });

function frame(id: string, title: string, caption: string, kind: string, drawing: ElementContent[]): Element {
  return el('figure', { className: ['fig', 'fig-prose'], id, ariaLabelledBy: [`${id}-title`], dataFigKind: kind }, [
    el('p', { className: ['fig__eyebrow'], ariaHidden: 'true' }, [text('Fig')]),
    el('p', { className: ['fig__title'], id: `${id}-title` }, [text(title)]),
    el('div', { className: ['fig__drawing'] }, drawing),
    el('figcaption', { className: ['fig__caption'] }, [text(caption)]),
  ]);
}

/** The release a rendered H2 heads, by its "[version]" text. */
function releaseOf(h2: Element, releases: Release[]): Release | undefined {
  const t = hastText(h2);
  return releases.find((r) => t.includes(`[${r.version}]`));
}

function timelineFigure(releases: Release[], ids: Map<string, string>, id: string): Element {
  const kinds = kindsInUse(releases);
  const max = Math.max(...releases.flatMap((r) => kinds.map((k) => kindCount(r, k))));
  const head = el('tr', {}, [
    el('th', { scope: 'col' }, [text('Release')]),
    ...kinds.map((k) => el('th', { scope: 'col' }, [text(k)])),
  ]);
  const rows = releases.map((r) => {
    const anchor = ids.get(r.version);
    const name: ElementContent[] = [anchor ? el('a', { href: `#${anchor}` }, [el('code', {}, [text(r.version)])]) : el('code', {}, [text(r.version)])];
    if (r.date) name.push(el('span', { className: ['release-line__date'] }, [text(r.date)]));
    return el('tr', {}, [
      el('th', { scope: 'row' }, name),
      ...kinds.map((k) => {
        const n = kindCount(r, k);
        return el('td', { className: ['release-line__cell'], dataKind: k }, n > 0 ? [pixelBarElement(n, max)] : [el('span', { className: ['release-line__none'] }, [text('—')])]);
      }),
    ]);
  });
  return frame(id, TIMELINE_TITLE, timelineCaption(releases), 'release-timeline', [
    el('div', { className: ['table-wrap'], role: 'region', tabIndex: 0, ariaLabel: `Table: ${TIMELINE_TITLE}` }, [
      el('table', { className: ['release-line'] }, [el('thead', {}, [head]), el('tbody', {}, rows)]),
    ]),
  ]);
}

function sectionFigure(r: Release, k: Release['kinds'][number], known: ReadonlySet<string>, id: string): Element {
  const diags = new Map(loadDiagnostics().map((d) => [d.code, d]));
  const parts: ElementContent[] = [];
  const { rows, none } = issueCounts(k);
  if (rows.length > 0) {
    const max = Math.max(...rows.map((x) => x.count), none);
    parts.push(
      el('p', { className: ['release-sec__label'] }, [text('Issues cited, with the number of entries citing each')]),
      el(
        'ul',
        { className: ['release-sec__issues'] },
        [...rows.map((x) => ({ label: `#${x.issue}`, count: x.count })), ...(none > 0 ? [{ label: 'none', count: none }] : [])].map((x) =>
          el('li', { className: ['release-sec__issue'] }, [
            el('span', { className: ['release-sec__issue-name'] }, [text(x.label)]),
            pixelBarElement(x.count, max),
          ]),
        ),
      ),
    );
  }
  const codes = sectionCodes(k, known);
  if (codes.length > 0) {
    parts.push(
      el('p', { className: ['release-sec__label'] }, [text('Diagnostic codes named')]),
      el('ul', { className: ['release-sec__codes'] }, codes.map((c) => el('li', {}, [diagnosticTileElement(diags.get(c)!)]))),
    );
  }
  return frame(id, sectionTitle(r, k), sectionCaption(r, k, known), 'release-section', parts);
}

/** Throws when the parser found kind sections of a release that the page did not render. */
function unrendered(rel: Release | undefined, kinds: Release['kinds']): void {
  if (rel && kinds.length > 0) throw new Error(`${RELEASE_NOTES_SOURCE}: ${rel.version} renders no heading for ${kinds.map((k) => `"### ${k.kind}"`).join(', ')}`);
}

/**
 * Draw the timeline before the first release heading, and under each long
 * kind section its figure (when it has one), then fold its entries after the
 * first SHOWN_ENTRIES.
 */
export function drawReleaseFigures(tree: Root, changelog: string, uid: (base: string) => string): void {
  const releases = parseReleases(changelog);
  const known = new Set(loadDiagnostics().map((d) => d.code));
  const kids = tree.children;
  const ids = new Map<string, string>();
  for (const k of kids) {
    if (!isEl(k, 'h2')) continue;
    const r = releaseOf(k, releases);
    if (r && typeof k.properties?.id === 'string') ids.set(r.version, k.properties.id);
  }
  let rel: Release | undefined;
  // The kind sections of the current release in order, matched to its H3s by
  // position, so two sections of the same kind each meet their own heading.
  let kinds: Release['kinds'] = [];
  for (let i = 0; i < kids.length; i++) {
    const node = kids[i]!;
    if (!isEl(node)) continue;
    if (node.tagName === 'h2') {
      unrendered(rel, kinds);
      rel = releaseOf(node, releases);
      kinds = rel ? [...rel.kinds] : [];
      continue;
    }
    if (node.tagName !== 'h3' || !rel) continue;
    const name = hastText(node).trim();
    const section = kinds.shift();
    if (!section || section.kind !== name) {
      throw new Error(`${RELEASE_NOTES_SOURCE}: ${rel.version} renders "### ${name}" where the parser found ${section ? `"### ${section.kind}"` : 'no more kind sections'}`);
    }
    // Every list between this H3 and the next heading: its items are the entries.
    const lists: number[] = [];
    for (let j = i + 1; j < kids.length; j++) {
      const k = kids[j]!;
      if (isEl(k) && /^h[1-6]$/.test(k.tagName)) break;
      if (isEl(k, 'ul') || isEl(k, 'ol')) lists.push(j);
    }
    const rendered = lists.reduce((n, j) => n + (kids[j] as Element).children.filter((c) => isEl(c, 'li')).length, 0);
    if (rendered !== section.entries.length) {
      throw new Error(`${RELEASE_NOTES_SOURCE}: ${rel.version} ${name} renders ${rendered} entries, the parser found ${section.entries.length}`);
    }
    if (section.entries.length < LONG_SECTION) continue;
    const j = kids.findIndex((k, n) => n > i && isEl(k));
    const list = kids[j];
    if (lists.length !== 1 || lists[0] !== j || !isEl(list, 'ul')) throw new Error(`${RELEASE_NOTES_SOURCE}: "### ${name}" under ${rel.version} is not followed by one list`);
    const items = list.children.filter((c): c is Element => isEl(c, 'li'));
    const rest = items.slice(SHOWN_ENTRIES);
    list.children = items.slice(0, SHOWN_ENTRIES);
    const more = el('details', { className: ['release-more'] }, [
      el('summary', {}, [text(`Show the other ${rest.length} entries under ${name} in ${rel.version}`)]),
      el('ul', {}, rest),
    ]);
    kids.splice(j + 1, 0, more);
    if (sectionHasFigure(section, known)) {
      kids.splice(i + 1, 0, sectionFigure(rel, section, known, uid(`ref-fig-release-${rel.version}-${name}`.toLowerCase().replace(/[^a-z0-9-]+/g, '-'))));
    }
  }
  unrendered(rel, kinds);
  const first = kids.findIndex((k) => isEl(k, 'h2'));
  kids.splice(first < 0 ? kids.length : first, 0, timelineFigure(releases, ids, uid('ref-fig-releases')));
}
