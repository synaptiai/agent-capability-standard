// The workflow figures (visual spec 3.3, F-W1 to F-W4) and the index strip
// (3.4, F-WI1). Expected values come from line scans of the catalog files and
// from a hand-written fixture workflow; never from the functions under test.
// The fixture is a JSON string, not a file: no YAML file may live under site/.
import { describe, expect, it } from 'vitest';
import { loadOntology } from '../src/data/ontology';
import { loadWorkflows, parseCatalog } from '../src/data/workflows';
import { dataFlowGrid, indexStripLabel, readLane, readsList, riskSummary, stripKey, workflowSpine } from '../src/lib/workflow-figures';
import { rowSlices } from '../src/pixel/lines';
import { workflowsIndexTwin, workflowTwin } from '../src/twins/workflows';
import { allCatalogSteps, catalogFiles, repoText } from './independent';
import { ALL_GRIDS, resolveGlyphKey } from '../src/pixel/keys';

// A 5-step workflow with a 2-step parallel group, a sub-workflow step, every
// gate action and every failure action (spec 6.3: the corpus cannot exercise these).
const FIXTURE = JSON.stringify({
  fixture_flow: {
    goal: 'Exercise every lane of the spine',
    risk: 'medium',
    inputs: { target: { type: 'string', required: true } },
    steps: [
      { capability: 'checkpoint', purpose: 'Save', store_as: 'cp_out', gates: [{ when: 'x', action: 'warn' }] },
      { capability: 'search', purpose: 'A', parallel_group: 'g1', store_as: 's1', input_bindings: { q: '${cp_out.id}' },
        failure_modes: [{ condition: 'a', action: 'stop' }, { condition: 'b', action: 'request_more_context' }] },
      { capability: 'search', purpose: 'B', parallel_group: 'g1', join: 'all_complete', store_as: 's2', input_bindings: { q: '${target}' },
        failure_modes: [{ condition: 'c', action: 'escalate' }] },
      { capability: 'mutate', purpose: 'Change', store_as: 'm', input_bindings: { a: '${s1}', b: '${s2}' },
        gates: [{ when: 'y', action: 'stop' }, { when: 'z', action: 'skip' }, { when: 'w', action: 'end' }],
        failure_modes: [{ condition: 'd', action: 'rollback' }, { condition: 'e', action: 'pause_and_checkpoint' }] },
      { capability: 'invoke', purpose: 'Run', workflow_id: 'other_flow', store_as: 'r', input_bindings: { m: '${m}', c: '${cp_out}' },
        gates: [{ when: 'v', action: 'rollback' }] },
    ],
  },
});
const fixture = () => parseCatalog('fixture.json', FIXTURE, 'core', loadOntology())[0]!;

describe('step spine on the fixture (F-W1)', () => {
  it('never lists one drawing twice with different words in its key', () => {
    // The issue #125 audit: "step rolls back" and "on failure, roll back" were the same undo glyph, and so
    // were "gate stops the run" and "on failure, stop". The fixture has every gate and failure action; a
    // rollback step is added so the role, gate and failure rollbacks all appear in one key.
    const wf = fixture();
    const rb = parseCatalog(
      'fixture.json',
      FIXTURE.replace('"steps":[', '"steps":[{"capability":"checkpoint","purpose":"Save first","store_as":"cp0"},').replace(
        /\]\}\}$/,
        ',{"capability":"rollback","purpose":"Undo","store_as":"rb","input_bindings":{"checkpoint":"${cp0}"}}]}}',
      ),
      'core',
      loadOntology(),
    )[0]!;
    expect(rb.steps.length).toBe(wf.steps.length + 2);
    const s = workflowSpine(rb);
    expect(s.legend.map((l) => l.glyph)).toEqual(expect.arrayContaining(['role:rollback', 'gate:rollback', 'fail:rollback', 'gate:stop', 'fail:stop']));
    const drawn = (k: string) => (k === 'pips' ? 'pips' : ALL_GRIDS[resolveGlyphKey(k)!]!.join('/'));
    const byDrawing = new Map<string, string>();
    const clashes: string[] = [];
    for (const l of s.legend) {
      const key = [l.marker, l.glyph].filter((x): x is string => !!x).map(drawn).join(' + ');
      const seen = byDrawing.get(key);
      if (seen !== undefined && seen !== l.label) clashes.push(`"${seen}" and "${l.label}"`);
      byDrawing.set(key, l.label);
    }
    expect(clashes).toEqual([]);
  });

  it('draws the parallel group as a fork bar, one row of two steps, and a join bar', () => {
    const s = workflowSpine(fixture());
    expect(s.rows.map((r) => r.kind)).toEqual(['step', 'fork', 'parallel', 'join', 'step', 'step']);
    const par = s.rows[2]!;
    expect(par.kind === 'parallel' && par.steps.map((x) => x.index)).toEqual([2, 3]);
    const join = s.rows[3]!;
    expect(join.kind === 'join' && join.join).toBe('all_complete');
    expect([...s.rowOf.entries()]).toEqual([[1, 0], [2, 2], [3, 2], [4, 4], [5, 5]]);
  });

  it('draws one glyph per gate and per failure mode, and every action of both enums', () => {
    const s = workflowSpine(fixture());
    expect(s.steps.map((x) => x.gates)).toEqual([['warn'], [], [], ['stop', 'skip', 'end'], ['rollback']]);
    expect(s.steps.map((x) => x.failures)).toEqual([[], ['stop', 'request_more_context'], ['escalate'], ['rollback', 'pause_and_checkpoint'], []]);
    const glyphs = s.legend.map((l) => l.glyph);
    for (const a of ['stop', 'rollback', 'skip', 'warn', 'end']) expect(glyphs).toContain(`gate:${a}`);
    for (const a of ['stop', 'rollback', 'request_more_context', 'pause_and_checkpoint', 'escalate']) expect(glyphs).toContain(`fail:${a}`);
    expect(glyphs).toEqual(expect.arrayContaining(['fork', 'flow:join', 'flow:invoke', 'role:checkpoint', 'role:mutating']));
    expect(s.maxGates).toBe(3);
    expect(s.maxFailures).toBe(2);
  });

  it('brackets the checkpoint to the step that relies on it, and draws no rollback lane without a rollback step', () => {
    const s = workflowSpine(fixture());
    expect(s.checkpointSpans).toEqual([{ from: 0, to: 4, fromStep: 1, toStep: 4 }]);
    expect(s.lanes).toEqual({ checkpoint: true, rollback: false, gate: true, failure: true, reads: true });
    expect(s.title).toBe('Steps of fixture_flow: 5 steps, checkpoint at step 1');
  });

  it('reads the producers from the ${...} bindings', () => {
    const s = workflowSpine(fixture());
    expect(s.steps.map((x) => x.reads)).toEqual([[], [1], [], [2, 3], [1, 4]]);
    expect(readsList(s)).toEqual(['Step 2 reads from step 1.', 'Step 4 reads from steps 2 and 3.', 'Step 5 reads from steps 1 and 4.']);
    const g = dataFlowGrid(fixture(), s);
    expect(g.reads).toBe(5);
    expect(g.rows[3]!.cells).toEqual(['', 'read', 'read', 'store', ''].map((c) => c || null));
  });
});

// ------------------------------------------------------------ corpus scans

/** For each workflow, per step, the `action:` values under `gates:` and under `failure_modes:`, by indentation. */
function scanActions(): Map<string, { gates: string[]; failures: string[] }[]> {
  const out = new Map<string, { gates: string[]; failures: string[] }[]>();
  const { core, domain } = catalogFiles();
  for (const f of [core, ...domain]) {
    let steps: { gates: string[]; failures: string[] }[] | null = null;
    let block: { key: 'gates' | 'failures'; indent: number } | null = null;
    for (const l of repoText(f).split('\n')) {
      const top = /^([A-Za-z_][\w-]*):/.exec(l);
      if (top) {
        steps = top[1]!.startsWith('x-') ? null : [];
        if (steps) out.set(top[1]!, steps);
        block = null;
        continue;
      }
      if (!steps || /^\s*(#|$)/.test(l)) continue;
      const indent = l.length - l.trimStart().length;
      if (/^\s*- capability:/.test(l)) {
        steps.push({ gates: [], failures: [] });
        block = null;
        continue;
      }
      if (block && indent <= block.indent && !/^\s*- /.test(l.slice(block.indent))) block = null;
      if (block && indent < block.indent) block = null;
      const key = /^\s*(gates|failure_modes):/.exec(l);
      if (key) {
        block = { key: key[1] === 'gates' ? 'gates' : 'failures', indent };
        continue;
      }
      const action = /^\s*(?:- )?action:\s*(\w+)/.exec(l);
      if (action && block && steps.length > 0) steps.at(-1)![block.key].push(action[1]!);
    }
  }
  return out;
}

describe('spine lanes drawn row by row (F-W1, wrapped rows)', () => {
  it('cuts a drawing into rows, each in its own coordinates, and carries a line on past a row it crosses', () => {
    // A 2px line from y 10 to y 50 on 28px rows: 18px of it in row 0, which it leaves at the bottom,
    // and 22px in row 1, where it ends; nothing in row 2.
    const slices = rowSlices([{ x: 0, y: 10, w: 2, h: 40, ink: 'ink' }], 3, 28);
    expect(slices.map((s) => s.rects.map((r) => [r.y, r.h]))).toEqual([[[10, 18]], [[0, 22]], []]);
    expect(slices.map((s) => s.continues)).toEqual([[{ x: 0, w: 2, ink: 'ink' }], [], []]);
  });

  it("draws each reader's bracket from its first producer's row down to its own, with a tick in every producer row", () => {
    // Fixture rows: 0 step 1, 1 fork, 2 steps 2 and 3, 3 join, 4 step 4, 5 step 5.
    // Step 2 reads step 1; step 4 reads steps 2 and 3 (one row); step 5 reads steps 4 and 1. Step 3 reads only an input.
    const lane = readLane(workflowSpine(fixture()));
    const show = (k: number) => lane.find((x) => x.step === k)!.pieces.map((p) => `${p.row}:${p.line}${p.stub ? '+stub' : ''}`);
    expect(lane.map((x) => x.step)).toEqual([2, 4, 5]);
    expect(show(2)).toEqual(['0:top+stub', '1:through', '2:bottom+stub']);
    expect(show(4)).toEqual(['2:top+stub', '3:through', '4:bottom+stub']);
    expect(show(5)).toEqual(['0:top+stub', '1:through', '2:through', '3:through', '4:through+stub', '5:bottom+stub']);
    expect(lane.find((x) => x.step === 5)!.producers).toEqual([1, 4]);
  });
});

describe('step spine on the catalogs (F-W1)', () => {
  const scans = scanActions();
  const caps = allCatalogSteps();

  it('draws one gate glyph per gate action and one failure glyph per failure action, as the catalog files list them', () => {
    for (const wf of loadWorkflows().all) {
      const want = scans.get(wf.id)!;
      const s = workflowSpine(wf);
      expect(s.steps.map((x) => ({ gates: x.gates, failures: x.failures })), wf.id).toEqual(want);
      expect(s.lanes.failure, wf.id).toBe(want.some((x) => x.failures.length > 0));
    }
  });

  it('draws a rollback bracket from the checkpoint before each rollback step, and no rollback lane otherwise', () => {
    for (const wf of loadWorkflows().all) {
      const list = caps.get(wf.id)!;
      const want = list.flatMap((c, i) => {
        if (c !== 'rollback') return [];
        const cp = list.slice(0, i).lastIndexOf('checkpoint');
        return cp === -1 ? [] : [[cp + 1, i + 1]];
      });
      const s = workflowSpine(wf);
      expect(s.rollbackSpans.map((r) => [r.fromStep, r.toStep]), wf.id).toEqual(want);
      expect(s.lanes.rollback, wf.id).toBe(want.length > 0);
    }
  });

  it('draws model_deployment as the spec describes: checkpoint at 3 bracketing 4, rollback at 7, three stop gates on execute', () => {
    // Visual spec 5.1, exemplar 6.
    const s = workflowSpine(loadWorkflows().byId.get('model_deployment')!);
    expect(s.checkpointSpans.map((c) => [c.fromStep, c.toStep])).toEqual([[3, 4]]);
    expect(s.rollbackSpans.map((c) => [c.fromStep, c.toStep])).toEqual([[3, 7]]);
    expect(s.steps[3]!.gates).toEqual(['stop', 'stop', 'stop']);
  });
});

describe('risk summary (F-W3)', () => {
  it('reads declared and computed risk as the catalog files state them', () => {
    const { core, domain } = catalogFiles();
    for (const f of [core, ...domain]) {
      let id = '';
      const declared = new Map<string, string>();
      const computed = new Map<string, string>();
      for (const l of repoText(f).split('\n')) {
        const top = /^([A-Za-z_][\w-]*):/.exec(l);
        if (top) id = top[1]!;
        const d = /^ {2}risk:\s*(\w+)/.exec(l);
        if (d) declared.set(id, d[1]!);
        const c = /^\s+computed_risk:\s*(\w+)/.exec(l);
        if (c) computed.set(id, c[1]!);
      }
      for (const [wid, risk] of declared) {
        const wf = loadWorkflows().byId.get(wid);
        if (!wf) continue;
        const r = riskSummary(wf);
        expect(r.declared, wid).toBe(risk);
        expect(r.computed, wid).toBe(computed.get(wid) ?? null);
      }
    }
  });

  it('collapses when the values agree and shows each when they differ (spec 3.3 examples)', () => {
    const md = riskSummary(loadWorkflows().byId.get('model_deployment')!);
    expect(md.agree).toBe(true);
    expect(md.caption).toBe('Declared, computed and highest step risk are all high.');
    const dbg = riskSummary(loadWorkflows().byId.get('debug_code_change')!);
    expect(dbg.agree).toBe(false);
    expect(dbg.caption).toBe('The catalog declares medium; the highest step risk is high; the computed risk is high.');
    expect(dbg.title).toBe('Risk of debug_code_change: declared medium; highest step risk high, at step 8 (execute)');
  });
});

describe('Markdown copies', () => {
  it('give every workflow page a step map with one row per step, and the risk and data-flow blocks', () => {
    const caps = allCatalogSteps();
    for (const wf of loadWorkflows().all) {
      const md = workflowTwin(wf.id).markdown;
      expect(md, wf.id).toContain(`**Figure: Steps of ${wf.id}: `);
      // The risk figure is drawn only when declared, computed and step risk
      // disagree; otherwise the copy has the sentence the page prints.
      const r = riskSummary(wf);
      if (r.agree) expect(md, wf.id).toContain(r.sentence);
      else expect(md, wf.id).toContain(`**Figure: Risk of ${wf.id}: `);
      expect(md, wf.id).toContain('**Figure: Which step reads which stored output.**');
      const block = md.slice(md.indexOf('**Figure: Steps of'));
      const rows = block.split('\n\n')[1]!.split('\n').slice(2);
      expect(rows.length, wf.id).toBe(caps.get(wf.id)!.length);
    }
  });

  it('list the layers each workflow uses on the index copy, as its strip names them', () => {
    const md = workflowsIndexTwin().markdown;
    const layerOf = new Map(loadOntology().capabilities.map((c) => [c.id, c.layer]));
    for (const [id, list] of allCatalogSteps()) {
      const layers = [...new Set(list.map((c) => layerOf.get(c)!))];
      expect(md, id).toContain(`| ${list.length} | ${layers.join(', ')} |`);
      const wf = loadWorkflows().byId.get(id);
      if (wf) expect(indexStripLabel(wf), id).toContain(`uses layers ${layers.join(', ')}`);
    }
  });
});

describe('stripKey (F-C4 on capability pages)', () => {
  it('names the highlighted tile, a symbol tile, each role the other steps take and the gate bar, read off the fixture', () => {
    // The fixture's steps: checkpoint (role, gated), search, search (plain), mutate (role, gated), invoke (plain, gated).
    const key = stripKey([fixture()], 'search');
    expect(key.map((k) => k.kind)).toEqual(['here', 'symbol', 'role', 'role', 'gate']);
    expect(key.map((k) => (k.kind === 'role' ? k.role : null)).filter(Boolean)).toEqual(['checkpoint', 'mutating']);
    // The first plain step that is not search is invoke (step 5).
    expect(key[1]).toMatchObject({ kind: 'symbol', capability: 'invoke' });
  });

  it('leaves out a role only the highlighted capability takes', () => {
    // Highlighting mutate: its own steps are ringed, so "makes the change" is not in the key.
    expect(stripKey([fixture()], 'mutate').some((k) => k.kind === 'role' && k.role === 'mutating')).toBe(false);
  });
});
