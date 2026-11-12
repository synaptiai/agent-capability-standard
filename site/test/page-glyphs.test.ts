// Every page that a listing shows as a card has its own glyph (issue #125
// acceptance: no two different concepts share an icon). The expected set of
// pages is read from the route table: every row of a section that has a
// listing page, plus the RFC proposals and the community pages.
import { describe, expect, it } from 'vitest';
import { ROUTES, type Route } from '../src/lib/routes';
import { LISTING_GROUP_GLYPHS } from '../src/pixel/glyphs-groups';
import { PAGE_GLYPHS } from '../src/pixel/glyphs-pages';
import { resolveGlyphKey } from '../src/pixel/keys';

/** Templates whose card glyph is the glyph of their kind (a layer, a workflow, a domain, a Standard). */
const KIND_GLYPH = new Set(['capability', 'layer', 'workflow', 'domain', 'spec']);

const listingSections = new Set(ROUTES.filter((r) => r.template === 'listing').map((r) => r.section));
const carded = (r: Route) =>
  r.template !== 'listing' &&
  !KIND_GLYPH.has(r.template) &&
  (listingSections.has(r.section) || r.section === 'community' || (r.section === 'rfcs' && r.group === 'Proposals'));
const pages = ROUTES.filter(carded);

describe('page glyphs', () => {
  it('covers every page a listing or proposal card can show', () => {
    expect(pages.length).toBeGreaterThan(0);
    expect(pages.filter((r) => !PAGE_GLYPHS[r.url] || resolveGlyphKey(PAGE_GLYPHS[r.url]!) === null).map((r) => r.url)).toEqual([]);
  });

  it('names no page that has no route', () => {
    const urls = new Set(ROUTES.map((r) => r.url));
    expect(Object.keys(PAGE_GLYPHS).filter((u) => !urls.has(u))).toEqual([]);
  });

  it('draws no two pages with the same grid', () => {
    const byGrid = new Map<string, string[]>();
    for (const url of Object.keys(PAGE_GLYPHS)) {
      const grid = resolveGlyphKey(PAGE_GLYPHS[url]!)!;
      byGrid.set(grid, [...(byGrid.get(grid) ?? []), url]);
    }
    expect([...byGrid].filter(([, urls]) => urls.length > 1)).toEqual([]);
  });

  it('shares a grid with a group heading only for that group\'s own overview page', () => {
    // An overview card stands for its group (the EU AI Act overview is the EU
    // AI Act), so it may repeat the heading's glyph; no other card may.
    const shared = ROUTES.filter((r) => PAGE_GLYPHS[r.url] && r.group && LISTING_GROUP_GLYPHS[r.group])
      .filter((r) => resolveGlyphKey(PAGE_GLYPHS[r.url]!) === resolveGlyphKey(LISTING_GROUP_GLYPHS[r.group!]!))
      .map((r) => r.url);
    const firstOfGroup = shared.filter((u) => {
      const r = ROUTES.find((x) => x.url === u)!;
      return ROUTES.filter((x) => x.section === r.section && x.group === r.group).sort((a, b) => a.order - b.order)[0] === r;
    });
    expect(shared).toEqual(firstOfGroup);
  });
});
