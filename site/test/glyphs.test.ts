// The glyph set of the figures (visual spec 2.1 to 2.3). Expected values:
// the distance limits are typed from the spec text (2.1); the masks are
// computed here by a separate centring, not the module's; the keys the data
// needs are read by plain text scans of the Standard, the profiles, the
// catalog schema and the ontology.
import { readdirSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { checkGlyphKeys, findHexColours, neededGlyphKeys, statusGlyphKeys, withoutFences } from '../scripts/check-design-data.mjs';
import { PROPOSED_WORKFLOW_STATUS, STATUS_STYLES } from '../src/lib/status';
import { CONCEPT_GLYPHS, GLYPH_ALIASES, LAYER_GLYPHS, UI_GLYPHS } from '../src/pixel/glyphs';
import { gridMask, gridPairs, maskDistance } from '../src/pixel/grid';
import { ALL_GRIDS, chapterKey, principleKey, resolveGlyphKey, TOOL_GLYPHS } from '../src/pixel/keys';
import { coverage } from '../src/lib/home';
import { familyOrder } from '../src/review/sheet';
import { ontologyEdgeTriples, profileFiles, repoText, standardFileVersions } from './independent';

/** A 7x7 or 9x9 grid as the set of on cells in a 9x9 frame; a 7x7 grid sits one cell in. */
function cells(rows: readonly string[]): Set<number> {
  const off = rows.length === 7 ? 1 : 0;
  const out = new Set<number>();
  rows.forEach((row, y) => [...row].forEach((ch, x) => (ch === '#' || ch === '=' || ch === 'a') && out.add((y + off) * 9 + x + off)));
  return out;
}
const apart = (a: Set<number>, b: Set<number>) => [...a].filter((c) => !b.has(c)).length + [...b].filter((c) => !a.has(c)).length;

describe('glyph distinctness', () => {
  it('counts the cells two masks disagree on', () => {
    // By hand: '#.' over '.#' against '##' over '..' differ in the top-right and bottom-right cells.
    expect(maskDistance(gridMask(['#.', '.#'], 2), gridMask(['##', '..'], 2))).toBe(2);
    // '=' and 'a' are on; 'o' and '.' are off.
    expect(maskDistance(gridMask(['=a'], 2), gridMask(['oo'], 2))).toBe(2);
  });

  it('keeps every pair of glyphs at least as far apart as the spec requires', () => {
    // Visual spec 2.1: two 7x7 grids differ in at least 10 cells, two 9x9 grids
    // in at least 14, and a 7x7 grid centred in a 9x9 frame differs from every
    // 9x9 grid in at least 12.
    const limit = (a: number, b: number) => (a === 7 && b === 7 ? 10 : a === 9 && b === 9 ? 14 : 12);
    const grids = Object.entries(ALL_GRIDS).filter(([, r]) => r.length === 7 || r.length === 9);
    const close: string[] = [];
    for (let i = 0; i < grids.length; i++) {
      for (let j = i + 1; j < grids.length; j++) {
        const [an, ar] = grids[i]!;
        const [bn, br] = grids[j]!;
        const d = apart(cells(ar), cells(br));
        if (d < limit(ar.length, br.length)) close.push(`${an} and ${bn} differ in ${d} cells`);
      }
    }
    expect(grids.length).toBeGreaterThan(Object.keys(LAYER_GLYPHS).length);
    expect(close).toEqual([]);
  });

  it('keeps the pairs the maintainer found hard to tell apart at least 14 cells apart', () => {
    // The exemplar review (issue #125) named these pairs as confusable at
    // their spec limit (10 for two inline glyphs, 12 inline against concept).
    // The spec says a pair found confusable is redrawn whatever its distance
    // (5.2); 14, the limit for two concept glyphs, is the bar they now meet.
    const named = [
      ['close', 'type:open'],
      ['mark:soft_requires', 'mark:precedes'],
      ['risk:low', 'risk:medium'],
      ['risk:medium', 'risk:high'],
      ['risk:low', 'risk:high'],
      ['sun', 'type:open'],
      ['mark:enables', 'mark:alternative_to'],
      ['REASON', 'approve:blocked'],
      ['stop', 'chapter:decision-frameworks'],
    ];
    const close = named
      .map(([a, b]) => ({ a, b, d: apart(cells(ALL_GRIDS[a!]!), cells(ALL_GRIDS[b!]!)) }))
      .filter((p) => p.d < 14)
      .map((p) => `${p.a} and ${p.b} differ in ${p.d} cells`);
    expect(close).toEqual([]);
  });

  it('draws concepts the visual review found sharing an icon with different grids', () => {
    // The issue #125 visual review: one glyph meant two things on the same
    // page or legend. Each pair below is two different concepts.
    const pairs = [
      ['flow:condition', 'diamond'], // runs only if / has gates
      ['mark:required', 'stamp'], // required field / needs approval
      ['approve:human', 'stamp'], // a person carries it out / needs approval
      ['flag:overridable', 'undo'], // mutation may be declared false / rollback
      ['skill:composed', 'nested'], // composed skill / nested field
      ['flow:invoke', 'nested'], // runs another workflow / nested field
      ['flow:run', 'nested'], // the step runs / nested field
      ['count:edges', 'mark:enables'], // edge types / the enables edge
      ['chapter:references', 'section:guides'], // References chapter / Guides section
      ['approve:review', 'eye'], // a person reviews it / read-only
    ];
    const same = pairs.filter(([a, b]) => resolveGlyphKey(a!) === resolveGlyphKey(b!)).map(([a, b]) => `${a} = ${b}`);
    expect(same).toEqual([]);
  });

  it('agrees with the pair list the glyph sheet shows', () => {
    const pairs = gridPairs(ALL_GRIDS);
    const a = pairs[0]!;
    expect(a.distance).toBe(apart(cells(ALL_GRIDS[a.a]!), cells(ALL_GRIDS[a.b]!)));
    expect(pairs.every((p) => p.distance >= p.min)).toBe(true);
  });

  it('never stores the same grid twice; reuse goes through the alias map', () => {
    const seen = new Map<string, string>();
    const dup: string[] = [];
    for (const [k, rows] of Object.entries(ALL_GRIDS)) {
      const sig = rows.join('/');
      if (seen.has(sig)) dup.push(`${k} = ${seen.get(sig)}`);
      seen.set(sig, k);
    }
    expect(dup).toEqual([]);
    for (const k of Object.keys(GLYPH_ALIASES)) expect(k in ALL_GRIDS, k).toBe(false);
  });

  it('draws inline glyphs at 7x7 and concept glyphs at 9x9', () => {
    const bad = [
      ...Object.entries(UI_GLYPHS).filter(([k, r]) => k !== 'pip' && (r.length !== 7 || r.some((row) => row.length !== 7))),
      ...Object.entries(CONCEPT_GLYPHS).filter(([, r]) => r.length !== 9 || r.some((row) => row.length !== 9)),
    ].map(([k]) => k);
    expect(bad).toEqual([]);
  });
});

describe('glyph keys from the data', () => {
  const standards = standardFileVersions().map((v) => repoText(`spec/STANDARD-v${v}.md`));

  it('keys chapters by title, with 1.0.0 "Error Model" drawn as the diagnostic model, and appendices bare', () => {
    expect(chapterKey('9. Error Model')).toBe('chapter:diagnostic-model');
    expect(chapterKey('11. Versioning and Compatibility')).toBe('chapter:versioning-and-compatibility');
    expect(chapterKey('Appendix A: Layer Reference')).toBeNull();
    expect(principleKey('3.4 Composable Atoms')).toBe('principle:composable-atoms');
  });

  it('has a glyph for every numbered chapter of every Standard', () => {
    const h2s = standards.flatMap((t) => [...t.matchAll(/^## (\d+\. .+)$/gm)].map((m) => m[1]!));
    expect(h2s.length).toBeGreaterThan(0);
    expect(h2s.filter((h) => resolveGlyphKey(chapterKey(h)!) === null)).toEqual([]);
    // Every other H2 is an appendix.
    const other = standards.flatMap((t) => [...t.matchAll(/^## (?!\d+\. )(.+)$/gm)].map((m) => m[1]!));
    expect(other.filter((h) => !h.startsWith('Appendix'))).toEqual([]);
  });

  it('has a glyph for every domain profile and every trust-source type', () => {
    const stems = profileFiles().map((f) => f.replace(/^.*\//, '').replace(/\.yaml$/, ''));
    expect(stems.length).toBeGreaterThan(0);
    expect(stems.filter((s) => resolveGlyphKey(`domain:${s}`) === null)).toEqual([]);
    const types = new Set(
      profileFiles().flatMap((f) => {
        const text = repoText(`schemas/profiles/${f}`);
        const block = text.slice(text.indexOf('\ndomain_sources:'));
        const end = block.slice(1).search(/\n\S/);
        return [...(end === -1 ? block : block.slice(0, end + 1)).matchAll(/^\s+type:\s*(\w+)/gm)].map((m) => m[1]!);
      }),
    );
    expect(types.size).toBeGreaterThan(0);
    expect([...types].filter((t) => resolveGlyphKey(`source:${t}`) === null)).toEqual([]);
  });

  it('has a glyph for every design principle of the current Standard', () => {
    const text = standards[0]!;
    const section = text.slice(text.search(/^## 3\. /m), text.search(/^## 4\. /m));
    const h3s = [...section.matchAll(/^### (.+)$/gm)].map((m) => m[1]!);
    expect(h3s.length).toBeGreaterThan(0);
    expect(h3s.filter((h) => resolveGlyphKey(principleKey(h)) === null)).toEqual([]);
  });

  it('has a glyph for every gate and failure action in the catalog schema, and a mark for every edge type', () => {
    const schema = JSON.parse(repoText('schemas/workflow_catalog.schema.json'));
    const gates: string[] = schema.$defs.gate.properties.action.enum;
    const fails: string[] = schema.$defs.failure_mode.properties.action.enum;
    expect([...gates.map((a) => `gate:${a}`), ...fails.map((a) => `fail:${a}`)].filter((k) => resolveGlyphKey(k) === null)).toEqual([]);
    // gate:stop and fail:stop draw one shared grid (visual spec 2.3).
    expect(resolveGlyphKey('gate:stop')).toBe(resolveGlyphKey('fail:stop'));
    const types = new Set(ontologyEdgeTriples().map((e) => e.type));
    expect([...types].filter((t) => resolveGlyphKey(`mark:${t}`) === null)).toEqual([]);
  });

  it('has a glyph for every tool card on the home page', () => {
    const titles = coverage().tools.map((c) => c.title);
    expect(titles.filter((t) => !TOOL_GLYPHS[t] || resolveGlyphKey(TOOL_GLYPHS[t]!) === null)).toEqual([]);
  });

  it('has a status glyph for every badge style, and reports a status whose style has none', () => {
    const styles = [...new Set(Object.values(STATUS_STYLES))];
    expect(styles.filter((st) => resolveGlyphKey(`status:${st}`) === null)).toEqual([]);
    const values = new Map([
      ['Accepted', 'spec/RFC-0001.md'],
      [PROPOSED_WORKFLOW_STATUS, 'src/lib/status.ts'],
      ['Withdrawn', 'spec/RFC-0009.md'],
    ]);
    const keys = statusGlyphKeys(values, { ...STATUS_STYLES, Withdrawn: 'withdrawn' });
    expect(keys.map((k) => k.key)).toEqual(['status:accepted', 'status:proposed', 'status:withdrawn']);
    expect(checkGlyphKeys(keys, {})).toEqual(['glyph status:withdrawn (status "Withdrawn" (spec/RFC-0009.md)) has no grid in src/pixel/glyphs.ts']);
  });

  it('has the glyphs the skill, agent and directory-tree figures name', () => {
    for (const k of ['skill:capability', 'skill:composed', 'agent:explore', 'agent:general-purpose', 'folder', 'group']) expect(resolveGlyphKey(k), k).not.toBeNull();
  });

  it('reports a needed key with no grid and an alias with no target', () => {
    const problems = checkGlyphKeys([{ key: 'domain:astronomy', from: 'x.yaml' }], { 'gate:nap': 'snooze' }, ALL_GRIDS);
    expect(problems).toEqual([
      'glyph domain:astronomy (x.yaml) has no grid in src/pixel/glyphs.ts',
      'glyph alias gate:nap points at snooze, which has no grid',
    ]);
  });

  it('finds hex colours in figure components', () => {
    expect(findHexColours([{ path: 'a.astro', text: '<rect fill="#ff0000"/>\n<rect style="fill: var(--ink)"/>\n<a href="#ref-x">' }])).toEqual([
      'a.astro:1: "#ff0000" is a hex colour; use a token',
    ]);
  });

  it('names no figure component colour by hex', () => {
    const dir = 'src/components/fig';
    const files = readdirSync(dir).map((f) => ({ path: `${dir}/${f}`, text: readFileSync(`${dir}/${f}`, 'utf8') }));
    expect(findHexColours(files)).toEqual([]);
  });
});

describe('glyph sheet families', () => {
  it('puts every grid under exactly one family heading, and nothing under "Other shapes" today', () => {
    const fams = familyOrder();
    const keys = fams.flatMap((f) => f.glyphs.map((g) => g.key));
    const want = Object.entries(ALL_GRIDS).filter(([, r]) => r.length === 7 || r.length === 9).map(([k]) => k);
    expect([...keys].sort()).toEqual([...want].sort());
    expect(fams.map((f) => f.title)).not.toContain('Other shapes');
  });

  it('files a grid no family names under "Other shapes", last', () => {
    const grids = { a: ['#......', '.......', '.......', '.......', '.......', '.......', '.......'], b: ['......#', '.......', '.......', '.......', '.......', '.......', '.......'] };
    const fams = familyOrder(grids, [{ title: 'Firsts', keys: ['a', 'missing'] }]);
    expect(fams.map((f) => [f.title, f.glyphs.map((g) => g.key)])).toEqual([
      ['Firsts', ['a']],
      ['Other shapes', ['b']],
    ]);
  });
});

describe('withoutFences', () => {
  it('blanks the lines of fenced blocks, keeping the line count, so a fenced "## " is not a chapter', () => {
    const text = ['## 1. Introduction', '````markdown', '```', '## 2. Inside', '```', '````', '~~~', '## 3. Tilde', '~~~', '## 4. After'].join('\n');
    expect(withoutFences(text).split('\n')).toEqual(['## 1. Introduction', '', '', '', '', '', '', '', '', '## 4. After']);
    const keys = neededGlyphKeys({ standards: [{ path: 'x.md', text }], profiles: [], catalogSchema: { properties: {} }, edgeTypes: [] } as never);
    expect(keys.filter((k) => k.from.startsWith('x.md')).map((k) => k.from)).toEqual(['x.md: "## 1. Introduction"', 'x.md: "## 4. After"']);
  });
});
