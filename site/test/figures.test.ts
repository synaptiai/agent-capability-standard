// The data helpers behind the shared figure parts. Expected values are typed
// from the visual spec's rules (2.3 for type glyphs, 6.1 for the Markdown
// block) or read by text scans of the ontology and the profiles.
import { describe, expect, it } from 'vitest';
import { loadOntology } from '../src/data/ontology';
import { autonomyBlocks, edgeTypeCount, safetyRows, typeGlyphs } from '../src/lib/views';
import { figure } from '../src/twins/md';
import { laneOffsets, run, chevron, edgeRects } from '../src/pixel/lines';
import { ontologyEdgeTriples, profileFiles, repoText, symmetricEdgeTypes } from './independent';

describe('type glyphs (visual spec 2.3)', () => {
  it('maps each type string the spec lists to its families, in order', () => {
    // The strings contractRows() emitted at 824eea1 (spec 2.3), with the family each rule gives.
    const want: [string, string[]][] = [
      ['string', ['type:text']],
      ['object', ['type:record']],
      ['array of object', ['type:list']],
      ['any', ['type:open']],
      ['array', ['type:list']],
      ['number', ['type:number']],
      ['string|object', ['type:text', 'type:record']],
      ['integer', ['type:number']],
      ['array of string', ['type:list']],
      ['boolean', ['type:boolean']],
      ['string|array', ['type:text', 'type:list']],
      ['object|array', ['type:record', 'type:list']],
    ];
    expect(want.map(([t]) => [t, typeGlyphs(t)])).toEqual(want);
  });

  it('reads the annotation grammar: generics, nullable, unions, and no glyph for null', () => {
    expect(typeGlyphs('array<string>')).toEqual(['type:list']);
    expect(typeGlyphs('map<string, number>')).toEqual(['type:record']);
    expect(typeGlyphs('nullable<integer>')).toEqual(['type:number']);
    expect(typeGlyphs('union<string, map<string, array<number>>>')).toEqual(['type:text', 'type:record']);
    expect(typeGlyphs('unknown')).toEqual(['type:open']);
    expect(typeGlyphs('null')).toEqual([]);
    expect(typeGlyphs('widget')).toEqual([]);
  });

  it('gives a glyph to every type string in the ontology schemas and every name in the annotation grammar', () => {
    const ontologyTypes = new Set(
      [...repoText('schemas/capability_ontology.yaml').matchAll(/^\s+type:\s*([a-z|]+)\s*$/gm)]
        .map((m) => m[1]!)
        .filter((t) => !ontologyEdgeTriples().some((e) => e.type === t)),
    );
    const grammar = /\*\*Annotation grammar:\*\*([\s\S]*?)\. `integer`/.exec(repoText('spec/STANDARD-v1.1.0.md'))![1]!;
    const names = [...grammar.matchAll(/`([^`]+)`/g)].map((m) => m[1]!.replace(/…|\b[TKV]\b/g, 'string')); // the grammar's placeholders, filled in
    expect(ontologyTypes.size).toBeGreaterThan(0);
    expect(names.length).toBeGreaterThan(0);
    expect([...ontologyTypes, ...names].filter((t) => t !== 'null' && typeGlyphs(t).length === 0)).toEqual([]);
  });
});

describe('safety panel rows (F-C3)', () => {
  const blocks = () =>
    profileFiles().map((f) => {
      const text = repoText(`schemas/profiles/${f}`);
      const block = /^\s*block_autonomous:\n((?:\s+- .*\n?)+)/m.exec(text)?.[1] ?? '';
      return [...block.matchAll(/-\s*(\w+)/g)].map((m) => m[1]!);
    });

  it('counts the profiles that block each capability, by a scan of the profile files', () => {
    const lists = blocks();
    for (const cap of loadOntology().capabilities) {
      const want = lists.filter((l) => l.includes(cap.id)).length;
      expect(autonomyBlocks(cap.id).blocked.length, cap.id).toBe(want);
      expect(autonomyBlocks(cap.id).total).toBe(lists.length);
    }
  });

  it('says a checkpoint comes through a requires edge exactly when the flag is unset and the edge exists', () => {
    const requiresFromCheckpoint = new Set(ontologyEdgeTriples().filter((e) => e.type === 'requires' && e.from === 'checkpoint').map((e) => e.to));
    // Each node starts at an unindented "- id:" line; its flags are the two-space lines under it.
    const flagged = new Set<string>();
    let current = '';
    for (const line of repoText('schemas/capability_ontology.yaml').split('\n')) {
      const id = /^- id: (\w+)$/.exec(line);
      if (id) current = id[1]!;
      else if (/^\S/.test(line)) current = '';
      if (current && line === '  requires_checkpoint: true') flagged.add(current);
    }
    expect(flagged.size).toBeGreaterThan(0);
    for (const cap of loadOntology().capabilities) {
      const row = safetyRows(cap).find((r) => r.key === 'checkpoint')!;
      const viaEdge = !flagged.has(cap.id) && requiresFromCheckpoint.has(cap.id);
      expect(row.value === 'Yes, via requires edge', cap.id).toBe(viaEdge);
      expect(row.on, cap.id).toBe(flagged.has(cap.id) || requiresFromCheckpoint.has(cap.id));
    }
  });

  it('always has the six cells in the spec order, with "No" on every off cell', () => {
    for (const cap of loadOntology().capabilities) {
      const rows = safetyRows(cap);
      expect(rows.map((r) => r.key)).toEqual(['risk', 'mutation', 'checkpoint', 'approval', 'overridable', 'autonomy']);
      for (const r of rows.filter((x) => !x.on)) expect(r.value, `${cap.id} ${r.key}`).toBe('No');
    }
  });
});

describe('edge type counts', () => {
  it('counts a symmetric type once per pair and a directed type once per edge', () => {
    const triples = ontologyEdgeTriples();
    const symmetric = new Set(symmetricEdgeTypes());
    for (const info of loadOntology().edgeTypes) {
      const rows = triples.filter((e) => e.type === info.id);
      const want = symmetric.has(info.id) ? new Set(rows.map((e) => [e.from, e.to].sort().join(' '))).size : rows.length;
      expect(edgeTypeCount(info), info.id).toBe(want);
    }
  });
});

describe('figure geometry', () => {
  it('cuts dashed runs 6 on, 4 off and dotted runs 2 on, 4 off', () => {
    expect(run(0, 10, 20, 10, 'ink', 2, 'dashed').map((r) => [r.x, r.w])).toEqual([
      [0, 6],
      [10, 6],
    ]);
    expect(run(0, 10, 12, 10, 'ink', 2, 'dotted').map((r) => [r.x, r.w])).toEqual([
      [0, 2],
      [6, 2],
    ]);
    expect(() => run(0, 0, 4, 4, 'ink')).toThrow('horizontal or vertical');
  });

  it('draws a 3-step chevron of five cells with its tip at the given point', () => {
    const c = chevron(20, 10, 'right', 'ink');
    expect(c).toHaveLength(5);
    expect(Math.max(...c.map((r) => r.x + r.w))).toBe(21);
    expect(Math.min(...c.map((r) => r.y))).toBe(5);
  });

  it('draws requires at 4px and leaves a gap in conflicts_with for its mark', () => {
    expect(edgeRects('requires', 0, 16, 60, 16).rects[0]!.h).toBe(4);
    const c = edgeRects('conflicts_with', 0, 16, 60, 16).rects;
    expect(c.some((r) => r.x <= 30 && r.x + r.w >= 30)).toBe(false);
  });

  it('lays out only the lanes a row uses', () => {
    const x = laneOffsets([
      { id: 'checkpoint', used: false },
      { id: 'rollback', used: true },
      { id: 'gate', used: true },
    ]);
    expect([...x]).toEqual([
      ['rollback', 0],
      ['gate', 8],
    ]);
  });
});

describe('figure blocks in Markdown copies (visual spec 6.1)', () => {
  it('writes the title, the caption and the table', () => {
    expect(figure('Relationships of mutate.', 'mutate has 2 relationships.', '| a |\n| --- |\n| b |\n')).toBe(
      '**Figure: Relationships of mutate.** mutate has 2 relationships.\n\n| a |\n| --- |\n| b |',
    );
  });
});

describe('figure parts as hast, for rehype steps', () => {
  it('draws a glyph as the same rects as its grid, hidden unless labelled', async () => {
    const { glyphElement } = await import('../src/pixel/hast');
    const { toRects, parseGrid } = await import('../src/pixel/grid');
    const { UI_GLYPHS } = await import('../src/pixel/glyphs');
    const g = glyphElement('flag', { scale: 3 });
    expect(g.children).toHaveLength(toRects(parseGrid('flag', UI_GLYPHS.flag!)).length);
    expect(g.properties.width).toBe(21);
    expect(g.properties.ariaHidden).toBe('true');
    expect(glyphElement('gate:stop', { label: 'stop' }).properties).toMatchObject({ role: 'img', ariaLabel: 'stop', dataGlyph: 'gate:stop' });
  });

  it('names a tile by its id and the layer the ontology gives it', async () => {
    const { miniTileElement } = await import('../src/pixel/hast');
    const layer = /^- id: mutate\n {2}layer: (\w+)$/m.exec(repoText('schemas/capability_ontology.yaml'))![1];
    const t = miniTileElement('mutate', { size: 32, relation: 'requires' });
    expect(t.tagName).toBe('a');
    // A linked tile is named by its own hidden text, not an aria-label that
    // would leave out the visible symbol (WCAG 2.5.3); an image tile keeps one.
    expect(t.properties.ariaLabel).toBeUndefined();
    expect(JSON.stringify(t.children[1])).toContain(`mutate, ${layer} layer: requires`);
    expect(t.properties.className).toEqual(['mini-tile', 'mini-tile--32', 'has-layer']);
    expect(t.children).toHaveLength(3);
    expect(miniTileElement('mutate', { size: 24, link: false }).properties).toMatchObject({ role: 'img', ariaLabel: `mutate, ${layer} layer` });
    expect(() => miniTileElement('teleport')).toThrow('not a capability');
  });

  it('fills a bar to its share of the scale and prints the value', async () => {
    const { pixelBarElement } = await import('../src/pixel/hast');
    const b = pixelBarElement(0.25, 1, { digits: 2 });
    const track = b.children[0] as import('hast').Element;
    expect((track.children[0] as import('hast').Element).properties.style).toBe('width: 25.000%');
    expect(JSON.stringify(b.children[1])).toContain('0.25');
  });
});
