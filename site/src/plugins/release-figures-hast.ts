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

/** The source whose page gets these figures. */
export const RELEASE_NOTES_SOURCE = 'CHANGELOG.md';

const el = (tagName: string, properties: Element['properties'], children: ElementContent[] = []): Element => ({
  type: 'element',
  tagName,
  properties,
  children,
});
const text = (value: string): ElementContent => ({ type: 'text', value });
const isEl = (n: unknown, tag?: string): n is Element =>
  typeof n === 'object' && n !== null && (n as Element).type === 'element' && (tag === undefined || (n as Element).tagName === tag);

function textOf(n: ElementContent | Element): string {
  if (n.type === 'text') return n.value;
  if (n.type === 'element') return n.children.map((c) => textOf(c)).join('');
  return '';
}

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
  const t = textOf(h2);
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
  for (let i = 0; i < kids.length; i++) {
    const node = kids[i]!;
    if (!isEl(node)) continue;
    if (node.tagName === 'h2') {
      rel = releaseOf(node, releases);
      continue;
    }
    if (node.tagName !== 'h3' || !rel) continue;
    const name = textOf(node).trim();
    const section = rel.kinds.find((k) => k.kind === name);
    if (!section || section.entries.length < LONG_SECTION) continue;
    const j = kids.findIndex((k, n) => n > i && isEl(k));
    const list = kids[j];
    if (!isEl(list, 'ul')) throw new Error(`${RELEASE_NOTES_SOURCE}: "### ${name}" under ${rel.version} is not followed by a list`);
    const items = list.children.filter((c): c is Element => isEl(c, 'li'));
    if (items.length !== section.entries.length) {
      throw new Error(`${RELEASE_NOTES_SOURCE}: ${rel.version} ${name} renders ${items.length} entries, the parser found ${section.entries.length}`);
    }
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
  const first = kids.findIndex((k) => isEl(k, 'h2'));
  kids.splice(first < 0 ? kids.length : first, 0, timelineFigure(releases, ids, uid('ref-fig-releases')));
}
