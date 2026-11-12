// The Standard's site-drawn figures from §1 to §12 (visual spec 3.9), the
// run replay (3.0, test/runreplay in 6.3) and the slot placement. Expected
// values come from plain scans of the sources (the Standard's text, the
// fixtures' JSON, the schema and policy files) or from the spec's formulas,
// never from the code under test.
import { describe, expect, it } from 'vitest';
import { renderRepoFile } from './pipeline';
import { repoText } from './independent';
import { cutAtSlots, SLOTS_BY_VERSION, SPEC_SLOTS, SPEC_SLOTS_100 } from '../src/lib/spec-slots';
import { placeSlots } from '../src/plugins/rehype-spec-slots';
import { REPLAY_FIXTURES, replay } from '../src/lib/run-replay';
import * as D from '../src/lib/spec-dsl-figures';
import * as T from '../src/lib/spec-tail-figures';

const STD = 'spec/STANDARD-v1.1.0.md';
const text = repoText(STD);

/** The lines of a `### n ` section of the Standard, up to the next ### or ##. */
function section(src: string, n: string): string[] {
  const lines = src.split('\n');
  const i = lines.findIndex((l) => l.startsWith(`### ${n} `));
  const out: string[] = [];
  for (const l of lines.slice(i + 1)) {
    if (/^#{2,3} /.test(l)) break;
    out.push(l);
  }
  return out;
}

describe('figure slots', () => {
  it('puts one marker, or one start and end pair, for every slot of each version', async () => {
    for (const [version, slots] of Object.entries(SLOTS_BY_VERSION)) {
      const html = (await renderRepoFile(`spec/STANDARD-v${version}.md`)).code;
      const markers = [...html.matchAll(/data-fig-slot="([^"]+)" data-fig-at="(here|start|end)"/g)].map((m) => `${m[1]}:${m[2]}`);
      for (const s of slots) {
        const wrap = s.at !== 'heading' && s.at.place === 'wrap';
        expect(markers.filter((m) => m.startsWith(`${s.key}:`)), `${version} ${s.key}`).toEqual(wrap ? [`${s.key}:start`, `${s.key}:end`] : [`${s.key}:here`]);
      }
      expect(cutAtSlots(html, slots).filter((p) => p.key !== undefined)).toHaveLength(slots.length);
    }
  });

  it('places the wait replay directly before the paragraph that opens "Delays."', async () => {
    const html = (await renderRepoFile(STD)).code;
    expect(html).toMatch(/data-fig-slot="wait-replay" data-fig-at="here"><\/div>\s*<p><strong>Delays\.<\/strong>/);
  });

  it('fails when a block a slot names no longer starts with its recorded words', async () => {
    const edited = text.replace('**Delays.** A step may declare', '**Pauses.** A step may declare');
    await expect(renderRepoFile(STD, edited)).rejects.toThrow(/slot wait-replay: paragraph 6 of §5\.13 starts "Pauses\./);
  });

  it('lists the slots in page order', () => {
    // Expected order: the order of the section numbers in the Standard's headings.
    const order = (slots: typeof SPEC_SLOTS, src: string) => {
      const heads = [...src.matchAll(/^#{2,4} (\S+)/gm)].map((m) => m[1]!);
      return slots.map((s) => heads.indexOf(s.section.trim()));
    };
    for (const [slots, src] of [[SPEC_SLOTS, text], [SPEC_SLOTS_100, repoText('spec/STANDARD-v1.0.0.md')]] as const) {
      const idx = order(slots, src);
      expect(idx.every((x) => x >= 0)).toBe(true);
      expect([...idx].sort((a, b) => a - b)).toEqual(idx);
    }
  });

  it('reports a slot whose section is missing', () => {
    const problems = placeSlots({ type: 'root', children: [] }, [{ key: 'x', level: 3, section: '9.9 ', at: 'heading' }]);
    expect(problems).toEqual(['slot x: expected one h3 starting "9.9 "']);
  });
});

describe('run replay (RunReplay, F-S14b, F-S16b, F-S18)', () => {
  type Fixture = {
    catalog: Record<string, { steps: { capability: string }[] }>;
    workflow: string;
    script: { expect: { kind: string; capability?: string; step?: number } }[];
    end: { kind: string; code?: string; outcome?: string; deferred?: { step: number; reason?: string }[] };
  };
  const read = (name: string) => JSON.parse(repoText(`tests/conformance/runtime/${name}.json`)) as Fixture;

  it.each(Object.values(REPLAY_FIXTURES))('marks %s as its script and end record it', (name) => {
    const f = read(name);
    const r = replay(name);
    const steps = f.catalog[f.workflow]!.steps;
    expect(r.steps).toHaveLength(steps.length);
    // Every request is counted once, on a step.
    expect(r.steps.reduce((a, s) => a + s.requests, 0)).toBe(f.script.length);
    // A request that names its step lands on it (fixture steps are 0-based, the figure's 1-based).
    for (const e of f.script.filter((x) => typeof x.expect.step === 'number')) expect(r.steps[e.expect.step!]!.requests).toBeGreaterThan(0);
    // A request for a capability lands on a step of that capability.
    for (const cap of new Set(f.script.map((x) => x.expect.capability).filter(Boolean))) {
      const want = f.script.filter((x) => x.expect.capability === cap).length;
      expect(r.steps.filter((s) => s.step.capability === cap).reduce((a, s) => a + s.requests, 0), cap).toBe(want);
    }
    // Deferred steps are exactly end.deferred, with its reasons.
    const deferred = (f.end.deferred ?? []).map((d) => d.step + 1);
    expect(r.steps.filter((s) => s.status === 'deferred').map((s) => s.n)).toEqual(deferred);
    for (const d of f.end.deferred ?? []) if (d.reason) expect(r.steps[d.step]!.reason).toBe(d.reason);
    expect(r.end).toEqual({ kind: f.end.kind, code: f.end.code ?? null, outcome: f.end.outcome ?? null });
  });

  it('draws the loop of recovery_loop_exhausted back to its goto_step, as many times as the script repeats the target', () => {
    const f = read('recovery_loop_exhausted');
    const plan = f.script.filter((x) => x.expect.capability === 'plan').length;
    const r = replay('recovery_loop_exhausted');
    expect(r.loops).toHaveLength(plan - 1);
    expect(r.loops[0]).toMatchObject({ from: 2, to: 1, maxLoops: 1 });
  });

  it('gives a step deferred without a reason the reason its own approval plan gives', () => {
    const r = replay('deferral_defers_effects');
    const first = r.steps.find((s) => s.status === 'deferred')!;
    expect(first.reason).toMatch(/defer_to_queue/);
  });
});

describe('Standard figure data', () => {
  it('counts the requirement keywords of each chapter as a line scan does (F-S0)', () => {
    // Expected: uppercase whole words outside fences, per "## N." chapter, §1.2 left out.
    const want = new Map<number, number>();
    let ch = 0;
    let fence = false;
    let skip = false;
    for (const l of text.split('\n')) {
      if (l.startsWith('```')) fence = !fence;
      if (fence || l.startsWith('```')) continue;
      const h = /^## (\d+)\./.exec(l);
      if (h) ch = Number(h[1]);
      else if (l.startsWith('## ')) ch = 0;
      if (l.startsWith('## ')) skip = false;
      if (l.startsWith('### ')) skip = l.startsWith('### 1.2 ');
      if (ch && !skip) want.set(ch, (want.get(ch) ?? 0) + (l.match(/\b(MUST|SHALL|REQUIRED)\b/g) ?? []).length);
    }
    const got = D.chapterKeywords(text);
    expect(Object.fromEntries(got.map((c) => [c.n, c.counts.must]))).toEqual(Object.fromEntries(want));
  });

  it('draws the decay columns as max(0.5 ** k, min_trust) with the trust model values (F-S25)', () => {
    const model = repoText('schemas/authority_trust_model.yaml');
    const min = Number(/^\s+min_trust:\s*([\d.]+)/m.exec(model)![1]);
    const days = Number(/^\s+half_life:\s*P(\d+)D/m.exec(model)![1]);
    const d = T.decayColumns(text, STD);
    expect(d.columns).toHaveLength(9);
    d.columns.forEach((c, i) => {
      expect(c.halfLives).toBe(i / 2);
      expect(c.days).toBe((i / 2) * days);
      expect(c.value).toBeCloseTo(Math.max(0.5 ** (i / 2), min), 10);
    });
  });

  it('has one tree branch per ├── or └── line of the §12.1 fence, and the leaves the fence ends lines with (F-S31)', () => {
    const lines = section(text, '12.1').filter((l) => /[├└]── /.test(l));
    const t = T.decisionTree(text, STD);
    const count = (n: T.TreeNode): number => n.branches.reduce((a, b) => a + 1 + count(b.node), 0);
    expect(count(t)).toBe(lines.length);
    expect(lines.some((l) => l.endsWith('→ Checkpoint REQUIRED'))).toBe(true);
  });

  it('lists each level the bullets §10.2 gives it (F-S28)', () => {
    const lines = section(text, '10.2');
    const want: Record<string, number> = {};
    let cur = '';
    for (const l of lines) {
      const m = /^\*\*(L\d) /.exec(l);
      if (m) cur = m[1]!;
      else if (cur && l.startsWith('- ')) want[cur] = (want[cur] ?? 0) + 1;
    }
    expect(Object.fromEntries(T.conformanceLevels(text, STD).map((c) => [c.level, c.items.length]))).toEqual(want);
  });

  it('weighs each trust class as authority_trust_model.yaml does and marks the §5.17 example classes (F-S21)', () => {
    const model = repoText('schemas/authority_trust_model.yaml');
    const block = /^trust_classes:\n  weights:\n((?:    .+\n)+)/m.exec(model)![1]!;
    const want = Object.fromEntries([...block.matchAll(/^\s+(\w+):\s*([\d.]+)/gm)].map((m) => [m[1]!, Number(m[2])]));
    const bars = D.trustClassBars(text, STD);
    expect(Object.fromEntries(bars.map((b) => [b.cls, b.weight]))).toEqual(want);
    const fence = section(text, '5.17').join('\n');
    const accept = /accept_trust_classes: \[([^\]]+)\]/.exec(fence)![1]!.split(',').map((x) => x.trim());
    expect(bars.filter((b) => b.accepted).map((b) => b.cls).sort()).toEqual(accept.sort());
  });

  it('draws one extension tile per schema enum value, each with the sections its table row names (F-S12)', () => {
    const schema = JSON.parse(repoText('schemas/workflow_catalog.schema.json'));
    const want = schema.$defs.workflow.properties.workflow_extensions.properties.requires.items.enum as string[];
    const rows = section(text, '5.9').filter((l) => /^\| `\w+@\d+`/.test(l));
    const tiles = D.extensionTiles(text, STD);
    expect(tiles.map((t) => t.id)).toEqual(want);
    for (const r of rows) {
      const id = /`(\w+@\d+)`/.exec(r)![1]!;
      expect(tiles.find((t) => t.id === id)!.sections).toEqual([...r.matchAll(/§(\d+(?:\.\d+)*)/g)].map((m) => m[1]));
    }
  });

  it('puts every capability §3.3 backticks in the safety ordering (F-S1)', () => {
    const caps = new Set([...repoText('schemas/capability_ontology.yaml').matchAll(/^\s*- id: (\w+)/gm)].map((m) => m[1]!));
    const named = [...section(text, '3.3').join('\n').matchAll(/`(\w+)`/g)].map((m) => m[1]!).filter((c) => caps.has(c));
    const drawn = new Set(D.safetyOrder().flatMap((g) => [g.source, ...g.edges.flatMap((e) => e.targets)]));
    expect(named.length).toBeGreaterThan(0);
    expect(named.filter((c) => !drawn.has(c))).toEqual([]);
  });

  it('checks the wait example against its own rule, interval × failure_threshold below the timeout (F-S15)', () => {
    const w = D.waitTimeline(text, STD);
    expect(w).toMatchObject({ timeout: '2h', interval: '10m', threshold: 3, lostAt: 30, timeoutMin: 120 });
    const broken = text.replace('liveness: {mode: probe, interval: 10m, failure_threshold: 3}', 'liveness: {mode: probe, interval: 1h, failure_threshold: 3}');
    expect(() => D.waitTimeline(broken, STD)).toThrow(/interval × failure_threshold/);
  });

  it('reads the precedence ladder of §5.8.1 loosest first (F-S11)', () => {
    // Expected: the spec's ladder (visual spec 3.9 F-S11).
    expect(D.precedenceLadder(text, STD).map((r) => r.rule)).toEqual(['or_expr', 'and_expr', 'cmp_expr', 'unary', 'primary']);
  });
});
