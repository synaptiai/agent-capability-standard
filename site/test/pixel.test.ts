// Pixel grids, the checks on design data, and the image encoders. Expected
// rectangles are worked out by hand from the grids; expected layer ids come
// from the CLAUDE.md layer table, read at test time.
import { readFileSync } from 'node:fs';
import { inflateSync } from 'node:zlib';
import { describe, expect, it } from 'vitest';
import {
  checkGrids,
  checkLayers,
  checkStatuses,
  findHandTypedCounts,
  ontologyLayers,
  sourceStatuses,
} from '../scripts/check-design-data.mjs';
import { LAYER_GLYPHS, MARK } from '../src/pixel/glyphs';
import { parseGrid, toRects } from '../src/pixel/grid';
import { encodePng, Raster } from '../src/pixel/png';
import { PROPOSED_WORKFLOW_STATUS, STATUS_STYLES, statusStyle } from '../src/lib/status';
import { claudeLayerTable, repoText } from './independent';

const tokensCss = readFileSync('src/styles/tokens.css', 'utf8');

describe('grids', () => {
  it('joins runs in a row and equal runs in consecutive rows', () => {
    const g = parseGrid('t', ['##.', '##.', '..a', '=.a']);
    expect(toRects(g)).toEqual([
      { x: 0, y: 0, w: 2, h: 2, paint: 'fg' },
      { x: 2, y: 2, w: 1, h: 2, paint: 'accent' },
      { x: 0, y: 3, w: 1, h: 1, paint: 'fg2' },
    ]);
  });

  it('does not join runs of different widths', () => {
    expect(toRects(parseGrid('t', ['##', '#.']))).toEqual([
      { x: 0, y: 0, w: 2, h: 1, paint: 'fg' },
      { x: 0, y: 1, w: 1, h: 1, paint: 'fg' },
    ]);
  });

  it('rejects ragged rows, unknown characters and empty grids', () => {
    expect(() => parseGrid('t', ['##', '#'])).toThrow('row 2 is 1 wide, expected 2');
    expect(() => parseGrid('t', ['#x'])).toThrow('unknown character "x"');
    expect(() => parseGrid('t', ['..'])).toThrow('nothing is painted');
    expect(() => parseGrid('t', [])).toThrow('no rows');
  });

  it('draws the mark as nine 3x3 blocks with the accent in the centre and the last block one unit out', () => {
    const rects = toRects(parseGrid('mark', MARK));
    expect(rects).toHaveLength(9);
    expect(rects.every((r) => r.w === 3 && r.h === 3)).toBe(true);
    expect(rects.filter((r) => r.paint === 'accent')).toEqual([{ x: 4, y: 4, w: 3, h: 3, paint: 'accent' }]);
    expect(rects.filter((r) => r.paint === 'fg2')).toEqual([{ x: 9, y: 9, w: 3, h: 3, paint: 'fg2' }]);
  });
});

describe('design data', () => {
  it('has a glyph and light and dark tokens for exactly the layers in CLAUDE.md', () => {
    const want = claudeLayerTable().map((r) => r.id).sort();
    expect(Object.keys(LAYER_GLYPHS).sort()).toEqual(want);
    expect(ontologyLayers(repoText('schemas/capability_ontology.yaml')).sort()).toEqual(want);
    expect(checkLayers(want, tokensCss, Object.keys(LAYER_GLYPHS))).toEqual([]);
  });

  it('reports a layer with no dark token and a glyph for no layer', () => {
    const css = tokensCss.replace(/(:root\[data-theme="dark"\] \{[\s\S]*?)\n\s*--layer-VERIFY: #86efac;/, '$1');
    const problems = checkLayers(['VERIFY', 'MODEL'], css, ['VERIFY', 'MODEL', 'EXTRA']);
    expect(problems).toContain('layer VERIFY has no dark token');
    expect(problems).toContain('glyph EXTRA is not an ontology layer');
  });

  it('reports a grid of the wrong size', () => {
    expect(checkGrids([{ label: 'layer glyph', grids: { X: ['#.', '.#'] }, size: [9, 9] }])).toEqual([
      'layer glyph X is 2x2, expected 9x9',
    ]);
  });

  it('reads status values the way the pages do and reports one with no style', () => {
    const files = [
      { path: 'docs/a.md', text: '# A\n\n**Document Status**: Normative \n' },
      { path: 'spec/RFC-0009-x.md', text: '**Status:** Withdrawn\n' },
      { path: 'spec/STANDARD-v9.0.0.md', text: '**Status:** Candidate Standard — accepted by\n' },
      { path: 'docs/guide.md', text: '**Status:** Template — adapt it\n' },
    ];
    const values = sourceStatuses(files);
    expect([...values.keys()]).toEqual(['Normative', 'Withdrawn', 'Candidate Standard']);
    expect(checkStatuses(values, STATUS_STYLES)).toEqual([
      'status "Withdrawn" (spec/RFC-0009-x.md) has no badge style in src/lib/status.ts',
    ]);
  });

  it('styles the label for undefined profile workflows and rejects unknown values', () => {
    expect(statusStyle(PROPOSED_WORKFLOW_STATUS)).toBe('proposed');
    expect(statusStyle(' Accepted ')).toBe('accepted');
    expect(() => statusStyle('Withdrawn')).toThrow('no badge style for "Withdrawn"');
  });

  it('finds counts typed next to the nouns and in CSS repeat()', () => {
    const files = [
      { path: 'a.astro', text: '<p>The standard has 36 atomic capabilities.</p>' },
      { path: 'b.css', text: '.t { grid-template-columns: repeat(9, 1fr); }\n.u { grid-template-columns: repeat(2, 1fr); }' },
      { path: 'c.ts', text: 'const n = layers.length; // one per layer' },
    ];
    expect(findHandTypedCounts(files, [9, 36])).toEqual([
      'a.astro:1: "36 atomic capabilities" types a count by hand',
      'b.css:1: "repeat(9," types a count by hand; set it from the data',
    ]);
  });
});

describe('PNG encoder', () => {
  it('writes the signature, the size and the pixels', () => {
    const r = new Raster(3, 2, [255, 255, 255]);
    r.fill(1, 0, 1, 2, [0, 0, 0]);
    const png = encodePng(r);
    expect([...png.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    expect(png.readUInt32BE(16)).toBe(3);
    expect(png.readUInt32BE(20)).toBe(2);
    const idatLen = png.readUInt32BE(33);
    const raw = inflateSync(png.subarray(41, 41 + idatLen));
    // Each row: filter byte 0, then white, black, white.
    const row = [0, 255, 255, 255, 0, 0, 0, 255, 255, 255];
    expect([...raw]).toEqual([...row, ...row]);
  });
});
