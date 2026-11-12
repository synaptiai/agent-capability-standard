// The Mermaid renderer: parser, layout, drawing, the build's failure on
// syntax it cannot draw, and the Markdown copy. Expected values come from the
// hand-written fixtures below (counted by hand), from the layout budgets the
// design states (46rem column, 360px phone), and from line scans of the
// repository's Markdown, never from the renderer's own output.
import { toHtml } from 'hast-util-to-html';
import { describe, expect, it } from 'vitest';
import { layoutDiagram, NARROW_BUDGET, WIDE_BUDGET, type Layout } from '../src/lib/mermaid/layout';
import { MermaidError, parseMermaid } from '../src/lib/mermaid/parse';
import { edgeRects, figureElement, shapeRects } from '../src/lib/mermaid/render';
import { describeDiagram } from '../src/lib/mermaid/text';
import { layoutsFor } from '../src/plugins/remark-mermaid';
import { markdownCopy } from '../src/twins/md';
import { readRepoFile } from '../src/lib/repo';
import { renderRepoFile } from './pipeline';

// 6 nodes (a..f), 8 links (the last line is two), 1 subgraph holding c and d.
const FIXTURE = `---
title: Fixture flow
---
flowchart TD
  %% a comment
  a[Start here] --> b{Is it valid?}
  subgraph g1 [Outcomes]
    c(Keep it)
    d([Drop it])
  end
  b -->|yes| c
  b -- no --> d
  c -.-> e[[Report]]
  d ==> e
  e --- f[(Store)]
  a & f --> e
`;

describe('parseMermaid', () => {
  const d = parseMermaid(FIXTURE);

  it('reads the direction and the title', () => {
    expect(d.direction).toBe('TB');
    expect(d.title).toBe('Fixture flow');
    expect(d.description).toBeNull();
  });

  it('reads every node with its label and shape', () => {
    expect(d.nodes.map((n) => [n.id, n.label, n.shape])).toEqual([
      ['a', 'Start here', 'rect'],
      ['b', 'Is it valid?', 'decision'],
      ['c', 'Keep it', 'round'],
      ['d', 'Drop it', 'stadium'],
      ['e', 'Report', 'subroutine'],
      ['f', 'Store', 'cylinder'],
    ]);
  });

  it('puts a node in the subgraph it first appears in', () => {
    expect(d.nodes.filter((n) => n.group === 'g1').map((n) => n.id)).toEqual(['c', 'd']);
    // Body line 7: the frontmatter takes lines 1 to 3.
    expect(d.groups).toEqual([{ id: 'g1', label: 'Outcomes', parent: null, line: 7 }]);
    const inside = parseMermaid('flowchart LR\n  subgraph s [Side]\n    x[X]\n  end\n  x --> y');
    expect(inside.nodes.map((n) => [n.id, n.group])).toEqual([['x', 's'], ['y', null]]);
  });

  it('reads every link with its style, arrowhead and label, expanding & on both sides', () => {
    expect(d.edges.map((e) => [e.from, e.to, e.style, e.arrow, e.label])).toEqual([
      ['a', 'b', 'solid', true, null],
      ['b', 'c', 'solid', true, 'yes'],
      ['b', 'd', 'solid', true, 'no'],
      ['c', 'e', 'dotted', true, null],
      ['d', 'e', 'thick', true, null],
      ['e', 'f', 'solid', false, null],
      ['a', 'e', 'solid', true, null],
      ['f', 'e', 'solid', true, null],
    ]);
  });

  it('reads accTitle and accDescr, and LR', () => {
    const x = parseMermaid('flowchart LR\n accTitle: Named\n accDescr: Said in words.\n p --> q');
    expect([x.direction, x.title, x.description]).toEqual(['LR', 'Named', 'Said in words.']);
  });

  it('refuses a node placed in a subgraph after it appeared elsewhere', () => {
    const src = 'flowchart TB\n  a --> b\n  subgraph s [S]\n    a\n  end';
    expect(() => parseMermaid(src)).toThrow(MermaidError);
  });
});

describe('unsupported syntax', () => {
  // Each case: source, the 1-based body line the error must name, and a word the message must contain.
  const cases: [string, number, RegExp][] = [
    ['flowchart RL\n a --> b', 1, /direction RL/],
    ['sequenceDiagram\n A->>B: hi', 1, /only flowcharts/],
    ['flowchart TB\n a --> b\n classDef x fill:#f00', 3, /classDef/],
    ['flowchart TB\n a --> b\n style a fill:#f00', 3, /style/],
    ['flowchart TB\n a --> b\n click a "https://x"', 3, /click/],
    ['flowchart TB\n a --o b', 2, /circle and cross/],
    ['flowchart TB\n a <--> b', 2, /two-headed/],
    ['flowchart TB\n a>flag] --> b', 2, /asymmetric/],
    ['flowchart TB\n a[/lean/] --> b', 2, /parallelogram/],
    ['flowchart TB\n a:::hot --> b', 2, /classes/],
    ['flowchart TB\n a[x<br>y] --> b', 2, /HTML/],
    ['flowchart TB\n subgraph s [S]\n  direction LR\n  a\n end', 3, /direction inside/],
    ['%%{init: {}}%%\nflowchart TB\n a', 1, /directives/],
    ['---\nconfig:\n  theme: dark\n---\nflowchart TB\n a', 2, /only "title:"/],
    ['flowchart TB\n subgraph s [S]\n  a', 2, /not closed/],
    ['flowchart TB\n a ~~~ b', 2, /invisible/],
    ['flowchart TB\n a[label (with) parens] --> b', 2, /double quotes/],
  ];
  for (const [src, line, word] of cases) {
    it(`fails on ${JSON.stringify(src.split('\n')[line - 1]?.trim())} at line ${line}`, () => {
      let err: unknown;
      try {
        parseMermaid(src);
      } catch (e) {
        err = e;
      }
      expect(err).toBeInstanceOf(MermaidError);
      expect((err as MermaidError).line).toBe(line);
      expect((err as MermaidError).message).toMatch(word);
    });
  }

  it('accepts a quoted label with brackets', () => {
    expect(parseMermaid('flowchart TB\n a["f(x) [y]"] --> b').nodes[0]!.label).toBe('f(x) [y]');
  });
});

function boxesOverlap(a: { x: number; y: number; w: number; h: number }, b: typeof a): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

function checkGrid(l: Layout): void {
  const all = [
    l.width,
    l.height,
    ...l.nodes.flatMap((n) => [n.x, n.y, n.w, n.h]),
    ...l.groups.flatMap((g) => [g.x, g.y, g.w, g.h]),
    ...l.edges.flatMap((e) => e.points.flatMap((p) => [p.x, p.y])),
  ];
  expect(all.filter((v) => !Number.isInteger(v) || v % 2 !== 0)).toEqual([]);
  for (const e of l.edges) {
    for (let i = 1; i < e.points.length; i++) {
      const [a, b] = [e.points[i - 1]!, e.points[i]!];
      expect(a.x === b.x || a.y === b.y, `${e.from}->${e.to} segment ${i} is diagonal`).toBe(true);
    }
  }
}

describe('layoutDiagram', async () => {
  const d = parseMermaid(FIXTURE);
  const wide = await layoutDiagram(d);
  const narrow = await layoutDiagram(d, { direction: 'TB', wrapAt: 14 });

  it('puts every coordinate on even pixels and every link on straight runs', () => {
    checkGrid(wide);
    checkGrid(narrow);
  });

  it('places every node once, inside the drawing, with no two overlapping', () => {
    expect(wide.nodes.map((n) => n.id)).toEqual(['a', 'b', 'c', 'd', 'e', 'f']);
    for (const n of wide.nodes) {
      expect(n.x >= 0 && n.y >= 0 && n.x + n.w <= wide.width && n.y + n.h <= wide.height, n.id).toBe(true);
    }
    for (const [i, a] of wide.nodes.entries()) for (const b of wide.nodes.slice(i + 1)) expect(boxesOverlap(a, b), `${a.id}/${b.id}`).toBe(false);
  });

  it('starts and ends each link on the border of its two nodes', () => {
    const box = (id: string) => wide.nodes.find((n) => n.id === id)!;
    const onBorder = (p: { x: number; y: number }, b: ReturnType<typeof box>) =>
      p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h && (p.x === b.x || p.x === b.x + b.w || p.y === b.y || p.y === b.y + b.h);
    for (const e of wide.edges) {
      expect(onBorder(e.points[0]!, box(e.from)), `${e.from}->${e.to} start`).toBe(true);
      expect(onBorder(e.points.at(-1)!, box(e.to)), `${e.from}->${e.to} end`).toBe(true);
    }
  });

  it('keeps each node of a subgraph inside the subgraph box', async () => {
    const s = await layoutDiagram(parseMermaid('flowchart LR\n subgraph s [Side]\n  x[X] --> y[Y]\n end\n y --> z[Z]'));
    checkGrid(s);
    const g = s.groups[0]!;
    for (const id of ['x', 'y']) {
      const n = s.nodes.find((m) => m.id === id)!;
      expect(n.x > g.x && n.y > g.y && n.x + n.w < g.x + g.w && n.y + n.h < g.y + g.h, id).toBe(true);
    }
    const z = s.nodes.find((m) => m.id === 'z')!;
    expect(boxesOverlap(z, g)).toBe(false);
  });

  it('fits the page, and gives a phone layout only when the drawing is wider than a phone', async () => {
    // Four boxes left to right are wider than a phone (each is at least 48px,
    // with 36px between layers), so a top-to-bottom phone layout is added.
    const chain = parseMermaid('flowchart LR\n a[Load data] --> b[Check it] --> c[Fix it] --> d[Save it]');
    const both = await layoutsFor(chain);
    if (typeof both === 'string') throw new Error(both);
    expect(both.wide.width).toBeLessThanOrEqual(WIDE_BUDGET);
    expect(both.wide.width).toBeGreaterThan(NARROW_BUDGET);
    expect(both.narrow!.direction).toBe('TB');
    expect(both.narrow!.width).toBeLessThanOrEqual(NARROW_BUDGET);
    const small = await layoutsFor(parseMermaid('flowchart TB\n a[A] --> b[B]'));
    if (typeof small === 'string') throw new Error(small);
    expect(small.narrow).toBeNull();
    const tooWide = parseMermaid(`flowchart LR\n${Array.from({ length: 12 }, (_, i) => ` n${i}[A rather long label ${i}] --> n${i + 1}`).join('\n')}`);
    expect(await layoutsFor(tooWide)).toMatch(/px wide, more than the 684px/);
  });
});

describe('drawing', async () => {
  const d = parseMermaid(FIXTURE);
  const wide = await layoutDiagram(d);
  const html = toHtml(figureElement(d, wide, null, { id: 'mermaid-l9', fallbackTitle: 'Unused' }));

  it('names the SVG by the visible title and describes it with the text version', () => {
    expect(html).toMatch(/<figure class="fig fig-mermaid" aria-labelledby="mermaid-l9-title">/);
    expect(html).toMatch(/<p class="fig-mermaid__title" id="mermaid-l9-title">Fixture flow<\/p>/);
    expect(html).toMatch(/<svg[^>]*role="img"[^>]*aria-labelledby="mermaid-l9-title"[^>]*aria-describedby="mermaid-l9-text"/);
    expect(html).toMatch(/<ul id="mermaid-l9-text">/);
  });

  it('draws with rects only: no path, no dash array, no curve, no colour value', () => {
    const svg = /<svg[\s\S]*<\/svg>/.exec(html)![0];
    expect(svg).not.toMatch(/<path|<circle|<ellipse|<line|<polyline|<polygon|stroke-dasharray|#[0-9a-f]{3,6}\b|rgb\(/i);
    expect(svg).toMatch(/shape-rendering="crispEdges"/);
    const nums = [...svg.matchAll(/<rect x="(-?\d+)" y="(-?\d+)" width="(\d+)" height="(\d+)"/g)].flatMap((m) => m.slice(1).map(Number));
    expect(nums.length).toBeGreaterThan(0);
    expect(nums.filter((n) => n % 2 !== 0)).toEqual([]);
  });

  it('lists every link in the text version, in words', () => {
    const tv = describeDiagram(d, 'Unused');
    expect(tv.items).toEqual([
      'Group "Outcomes": Keep it, Drop it',
      'Start here → Is it valid?',
      'Is it valid? → Keep it: yes',
      'Is it valid? → Drop it: no',
      'Keep it → Report (dotted line)',
      'Drop it → Report (thick line)',
      'Report — Store (no arrowhead)',
      'Start here → Report',
      'Store → Report',
    ]);
    expect(tv.caption).toBe('6 boxes joined by 8 links, in 1 group, read top to bottom.');
    for (const item of tv.items) expect(html).toContain(`<li>${item.replace(/&/g, '&#x26;')}</li>`);
  });

  it('takes the title from the nearest heading when the diagram has none', () => {
    expect(describeDiagram(parseMermaid('flowchart TB\n a --> b'), 'Process Pattern').title).toBe('Diagram: Process Pattern');
  });

  it('draws a dotted link as 2px squares 6px apart, and a chevron of three steps', () => {
    const rects = edgeRects({ from: 'a', to: 'b', style: 'dotted', arrow: true, label: null, points: [{ x: 10, y: 0 }, { x: 10, y: 30 }] });
    // The line stops 6px short of the tip (y 24); squares at 0, 6, 12, 18; chevron rows at 24, 26, 28,
    // reaching 6, 4 and 2px past the 2px line on each side.
    expect(rects).toEqual([
      { x: 10, y: 0, w: 2, h: 2 },
      { x: 10, y: 6, w: 2, h: 2 },
      { x: 10, y: 12, w: 2, h: 2 },
      { x: 10, y: 18, w: 2, h: 2 },
      { x: 8, y: 28, w: 6, h: 2 },
      { x: 6, y: 26, w: 10, h: 2 },
      { x: 4, y: 24, w: 14, h: 2 },
    ]);
  });

  it('steps the corners of a round box instead of curving them', () => {
    // 8x6 cells of 2px: the top row is inset one cell, the next rows are not.
    const { line } = shapeRects('round', 16, 12);
    expect(line).toContainEqual({ x: 2, y: 0, w: 12, h: 2 });
    expect(line).toContainEqual({ x: 0, y: 2, w: 2, h: 8 });
    expect(line.some((r) => r.x === 0 && r.y === 0)).toBe(false);
  });
});

describe('in the build', () => {
  it('fails on syntax it cannot draw, naming the file and line', async () => {
    // Line 1 heading, 2 blank, 3 fence opens, 4 header, 5 the bad link.
    const text = '# Title\n\n```mermaid\nflowchart TB\n  a --x b\n```\n';
    await expect(renderRepoFile('docs/WORKFLOW_PATTERNS.md', text)).rejects.toThrow(/docs\/WORKFLOW_PATTERNS\.md:5: circle and cross link ends/);
  });

  it('draws each mermaid fence of the two guides as a figure', async () => {
    for (const file of ['docs/GROUNDED_AGENCY.md', 'docs/WORKFLOW_PATTERNS.md']) {
      const fences = readRepoFile(file).split('\n').filter((l) => /^```mermaid\s*$/.test(l)).length;
      expect(fences, file).toBeGreaterThanOrEqual(3);
      const { code } = await renderRepoFile(file);
      expect([...code.matchAll(/<figure class="fig fig-mermaid"/g)].length, file).toBe(fences);
      expect(code, file).not.toMatch(/language-mermaid|data-language="mermaid"/);
    }
  });

  it('keeps each fence in the Markdown copy and adds its text version', () => {
    const text = '# Title\n\n## Process\n\n```mermaid\nflowchart LR\n  a[Load] -->|data| b[Save]\n```\n\nAfter.\n';
    const copy = markdownCopy('docs/WORKFLOW_PATTERNS.md', text);
    expect(copy).toContain('```mermaid\nflowchart LR\n  a[Load] -->|data| b[Save]\n```\n\n**Figure: Diagram: Process.** 2 boxes joined by 1 link, read left to right.\n\n- Load → Save: data\n\nAfter.');
  });
});
