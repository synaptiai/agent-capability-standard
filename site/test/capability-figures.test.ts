// Tests on what the capability page's figures show (visual spec 3.1, 6.3).
// Expected values come from line scans of the ontology and the SKILL.md
// files (test/independent.ts), from the spec's own reading of mutate at
// 824eea1 (a hand-written fixture), or from the spec's caption wording;
// never from the functions under test.
import { describe, expect, it } from 'vitest';
import { loadOntology } from '../src/data/ontology';
import {
  chainCaption,
  chainChecks,
  compositionChain,
  exampleFields,
  exampleFieldsIsFigure,
  contractRowId,
  contractSummary,
  edgeRules,
  outputFields,
  outputFieldsCaption,
  outputFieldsIsFigure,
  procedureMap,
  procedureMapCaption,
  procedureMapIsFigure,
  safetySequence,
  sequenceCaption,
  sequenceIsFigure,
  neighbourCounts,
  neighbourhoodCaption,
  neighbours,
  relationWords,
  splitAtH2s,
} from '../src/lib/capability-figures';
import { currentStandardText } from '../src/lib/spec-figures';
import { ontologyEdgeTriples, repoText, sectionLines, symmetricEdgeTypes } from './independent';

const o = loadOntology();
const cap = (id: string) => o.byId.get(id)!;

/** Each capability's relations by a scan: directed edges once per triple, symmetric types once per pair. */
function scannedRelations(): Map<string, { other: string; type: string; dir: 'in' | 'out' | 'both-ways' }[]> {
  const sym = new Set(symmetricEdgeTypes());
  const out = new Map<string, { other: string; type: string; dir: 'in' | 'out' | 'both-ways' }[]>();
  const add = (id: string, r: { other: string; type: string; dir: 'in' | 'out' | 'both-ways' }) => {
    const list = out.get(id) ?? [];
    if (!list.some((x) => x.other === r.other && x.type === r.type && x.dir === r.dir)) list.push(r);
    out.set(id, list);
  };
  for (const t of ontologyEdgeTriples()) {
    if (sym.has(t.type)) {
      add(t.from, { other: t.to, type: t.type, dir: 'both-ways' });
      add(t.to, { other: t.from, type: t.type, dir: 'both-ways' });
    } else {
      add(t.from, { other: t.to, type: t.type, dir: 'out' });
      add(t.to, { other: t.from, type: t.type, dir: 'in' });
    }
  }
  return out;
}

describe('neighbours (F-C1)', () => {
  const scanned = scannedRelations();

  it.each(o.capabilities.map((c) => c.id))('%s: one entry per neighbour, every relation once, as the edges block lists them', (id) => {
    const want = scanned.get(id) ?? [];
    const got = neighbours(cap(id));
    expect(got.map((n) => n.id).sort()).toEqual([...new Set(want.map((r) => r.other))].sort());
    const flat = got.flatMap((n) => n.relations.map((r) => `${n.id} ${r.type} ${r.direction}`)).sort();
    expect(flat).toEqual(want.map((r) => `${r.other} ${r.type} ${r.dir}`).sort());
  });

  it('groups mutate as the spec read it at 824eea1: 5 into, 3 out of, 12 relationships with 8 capabilities', () => {
    // Visual spec 3.1, "mutate at 824eea1 (probe mutateGroups)".
    const got = neighbours(cap('mutate'));
    const ids = (g: string) => got.filter((n) => n.group === g).map((n) => n.id).sort();
    expect(ids('into')).toEqual(['checkpoint', 'constrain', 'generate', 'plan', 'rollback']);
    expect(ids('out')).toEqual(['audit', 'persist', 'verify']);
    expect(ids('both')).toEqual([]);
    expect(ids('either')).toEqual([]);
    const rollback = got.find((n) => n.id === 'rollback')!;
    expect(rollback.relations.map((r) => r.type).sort()).toEqual(['conflicts_with', 'specializes']);
    expect(neighbourCounts(got)).toEqual({ relations: 12, capabilities: 8, into: 8, out: 3, bothWays: 1 });
    // Visual spec 6.1's sentence counted relations (8 into, 3 out, 1 both
    // ways) while the row headings count tiles (5, 3), and no "both ways" row
    // is drawn, so the review found they did not add up. The caption now counts
    // tiles per row, as the headings do, and names the symmetric edge drawn in
    // a directed row. Expected words from the edge list above, by hand.
    expect(neighbourhoodCaption(cap('mutate'), got)).toBe(
      'mutate has 12 relationships with 8 capabilities: 5 with edges into it and 3 with edges out of it; its conflicts_with edge with rollback runs both ways.',
    );
  });

  it('puts a neighbour with directed relations both ways in "both", and says which way each points', () => {
    // A capability with a directed edge to and from the same neighbour, found by the scan.
    const scan = scannedRelations();
    const pair = [...scan.entries()].flatMap(([id, rs]) =>
      rs.filter((r) => r.dir === 'in' && rs.some((x) => x.other === r.other && x.dir === 'out')).map((r) => [id, r.other] as const),
    )[0];
    expect(pair, 'the ontology has a pair of capabilities with directed edges both ways').toBeDefined();
    const [id, other] = pair!;
    const n = neighbours(cap(id)).find((x) => x.id === other)!;
    expect(n.group).toBe('both');
    expect(relationWords(n)).toMatch(/into it/);
    expect(relationWords(n)).toMatch(/out of it/);
  });

  it('puts a neighbour with only symmetric relations in "either"', () => {
    const scan = scannedRelations();
    const only = [...scan.entries()].flatMap(([id, rs]) => {
      const others = [...new Set(rs.map((r) => r.other))];
      return others.filter((x) => rs.filter((r) => r.other === x).every((r) => r.dir === 'both-ways')).map((x) => [id, x] as const);
    })[0];
    expect(only).toBeDefined();
    expect(neighbours(cap(only![0])).find((x) => x.id === only![1])!.group).toBe('either');
  });
});

describe('exampleFields (F-C9)', () => {
  it('marks the output fields each example fence uses as a key, read by hand', () => {
    const text = [
      '## Output Contract', '', '```yaml', 'result: object', 'confidence: number', 'notes: string', '```', '',
      '## Examples', '', '### Example 1: Small', '', '```yaml', 'result:', '  x: 1', 'confidence: 0.9', '```', '',
      '### Example 2: JSON', '', '```json', '{ "result": {}, "notes": "n" }', '```', '', 'The confidence is low.', '',
      '## Verification', '',
    ].join('\n');
    const f = exampleFields(text, 'fixture');
    expect(f.examples).toEqual([
      { title: 'Example 1: Small', shows: ['result', 'confidence'] },
      // "confidence" outside a fence does not count.
      { title: 'Example 2: JSON', shows: ['result', 'notes'] },
    ]);
    expect(exampleFieldsIsFigure(f)).toBe(true);
  });
});

describe('chainChecks', () => {
  it('reads the edges between the pair in either direction and counts neighbouring steps in order', () => {
    // Hand-made: two workflows; a runs right before b twice and right after b once.
    const o = loadOntology();
    const cap = o.byId.get('mutate')!;
    const wfs = [{ steps: [{ capability: 'checkpoint' }, { capability: 'mutate' }, { capability: 'verify' }] }, { steps: [{ capability: 'checkpoint' }, { capability: 'mutate' }, { capability: 'checkpoint' }] }];
    const checks = chainChecks(cap, { follows: ['checkpoint'], precedes: ['verify'] }, o, wfs);
    // Expected from the independent YAML scan: the edges between checkpoint and mutate, and between mutate and verify.
    const triples = ontologyEdgeTriples();
    const want = (a: string, b: string) => triples.filter((e) => (e.from === a && e.to === b) || (e.from === b && e.to === a)).map((e) => e.type).sort();
    expect(checks[0]!.edges.map((e) => e.type).sort()).toEqual(want('checkpoint', 'mutate'));
    expect(checks[0]!.adjacent).toBe(2);
    expect(checks[1]!.edges.map((e) => e.type).sort()).toEqual(want('mutate', 'verify'));
    expect(checks[1]!.adjacent).toBe(1);
  });
});

describe('composition text against the ontology', () => {
  it("never says a skill commonly follows a capability the ontology orders after it, or precedes one ordered before it", () => {
    // Issue #125 review: mutate's skill said it "commonly follows verify"
    // while the ontology's precedes edge puts verify after mutate. Expected:
    // no such pair, with edges read by the independent YAML scan.
    const before = new Set(ontologyEdgeTriples().filter((e) => e.type === 'precedes' || e.type === 'requires').map((e) => `${e.from}>${e.to}`));
    const bad: string[] = [];
    for (const c of loadOntology().capabilities) {
      const chain = compositionChain(repoText(`skills/${c.id}/SKILL.md`));
      for (const x of chain.follows) if (before.has(`${c.id}>${x}`)) bad.push(`${c.id} follows ${x}`);
      for (const x of chain.precedes) if (before.has(`${x}>${c.id}`)) bad.push(`${c.id} precedes ${x}`);
    }
    expect(bad).toEqual([]);
  });
});

describe('compositionChain', () => {
  /** A scan: for each "- " item under a label in Composition Patterns, the capability ids among the backticked words before its " - " description, or the first id of an item that opens with words. */
  function scan(text: string, label: string): string[] {
    const sec = text.split(/^## Composition Patterns\s*$/m)[1]?.split(/^## /m)[0] ?? '';
    const block = sec.split(`**${label}:**`)[1]?.split(/\n\s*\n/)[0] ?? '';
    const ids = block
      .split('\n')
      .filter((l) => l.startsWith('- '))
      .flatMap((l) => {
        const idsIn = (t: string) => [...t.matchAll(/`([a-z_]+)`/g)].map((m) => m[1]!).filter((x) => o.byId.has(x));
        // An item that opens with words ("May follow `observe` ...") names one.
        return l.startsWith('- `') ? idsIn(l.slice(2).split(' - ')[0]!) : idsIn(l).slice(0, 1);
      });
    return [...new Set(ids)];
  }

  it.each(o.capabilities.map((c) => c.id))('%s: the ids under "Commonly follows" and "Commonly precedes", in order', (id) => {
    const text = repoText(`skills/${id}/SKILL.md`);
    const got = compositionChain(text);
    expect(got.follows).toEqual(scan(text, 'Commonly follows'));
    expect(got.precedes).toEqual(scan(text, 'Commonly precedes'));
  });

  it('skips words that are not capability ids', () => {
    const text = ['## Composition Patterns', '', '**Commonly follows:**', '- `not_a_capability` - x', '- `plan` - y', '', '**Anti-patterns:**', '- `mutate`'].join('\n');
    expect(compositionChain(text)).toEqual({ follows: ['plan'], precedes: [] });
  });

  it('takes every id an item names before its description, and none from the description', () => {
    // Hand-written from rollback's and plan's lists: "`mutate` / `execute`" names two
    // capabilities; "(`plan` precedes both)" is description, not a listed neighbour.
    const text = ['## Composition Patterns', '', '**Commonly follows:**', '- `verify` - when `passed: false`', '- `mutate` / `execute` - if the side effect fails', '', '**Commonly precedes:**', '- `execute` / `mutate` - carry out the plan (`plan` precedes both)'].join('\n');
    expect(compositionChain(text)).toEqual({ follows: ['verify', 'mutate', 'execute'], precedes: ['execute', 'mutate'] });
  });

  it('rollback lists 7 capabilities, mutate and execute among them', () => {
    const c = compositionChain(repoText('skills/rollback/SKILL.md'));
    expect(c.follows.length + c.precedes.length).toBe(7);
    expect(c.follows).toEqual(expect.arrayContaining(['mutate', 'execute']));
  });
});

describe('splitAtH2s', () => {
  it('splits before each h2, keeps the heading apart from its body, and loses nothing', () => {
    const html = '<p>lead</p><h2 id="a">A<a class="heading-anchor"></a></h2><p>x</p><h3 id="c">C</h3><h2 id="b">B</h2><ul><li>y</li></ul>';
    const s = splitAtH2s(html);
    expect(s.lead).toBe('<p>lead</p>');
    expect(s.parts.map((p) => p.id)).toEqual(['a', 'b']);
    expect(s.parts[0]!.head).toBe('<h2 id="a">A<a class="heading-anchor"></a></h2>');
    expect(s.parts[0]!.body).toBe('<p>x</p><h3 id="c">C</h3>');
    expect(s.lead + s.parts.map((p) => p.head + p.body).join('')).toBe(html);
  });
});

describe('contractRowId', () => {
  it('keeps inputs and outputs apart and starts with ref-, as generated ids must', () => {
    expect(contractRowId('in', 'checkpoint_id')).toBe('ref-contract-in-checkpoint_id');
    expect(contractRowId('out', 'checkpoint_id')).not.toBe(contractRowId('in', 'checkpoint_id'));
  });
});

describe('edgeRules (F-C5)', () => {
  it('reads MUST/SHOULD and the diagnostic of each ordering type from the Standard\'s §4.3 tables', () => {
    // Hand-read from spec/STANDARD-v1.1.0.md §4.3 on 2026-11-12: the
    // "Enforcement" column and the first code of the "Diagnostic" column.
    const { text, source } = currentStandardText();
    expect(edgeRules(text, source)).toEqual({
      requires: { level: 'MUST', code: 'V102' },
      soft_requires: { level: 'SHOULD', code: 'W601' },
      precedes: { level: 'MUST', code: 'V102' },
      conflicts_with: { level: 'MUST', code: 'F504' },
    });
  });

  it('fails when a type has no row, rather than drawing a blank rule', () => {
    const text = ['### 4.3 Edges', '', '| Edge Type | Enforcement |', '|---|---|', '| `requires` | MUST |', '', '| Edge | Rule | Diagnostic |', '|---|---|---|', '| `requires` | x | V102 |', ''].join('\n');
    expect(() => edgeRules(text, 'fixture')).toThrow(/soft_requires/);
  });
});

describe('safetySequence (F-C5)', () => {
  const ordering = new Set(['requires', 'soft_requires', 'precedes']);

  it.each(o.capabilities.map((c) => c.id))('%s: before, after and apart are the ordering and conflicts_with edges the edges block lists', (id) => {
    const t = ontologyEdgeTriples();
    const s = safetySequence(cap(id));
    const flat = (side: { id: string; types: string[] }[]) => side.flatMap((x) => x.types.map((ty) => `${x.id} ${ty}`)).sort();
    expect(flat(s.before)).toEqual(t.filter((e) => e.to === id && ordering.has(e.type)).map((e) => `${e.from} ${e.type}`).sort());
    expect(flat(s.after)).toEqual(t.filter((e) => e.from === id && ordering.has(e.type)).map((e) => `${e.to} ${e.type}`).sort());
    const apart = new Set(t.filter((e) => e.type === 'conflicts_with' && (e.from === id || e.to === id)).map((e) => (e.from === id ? e.to : e.from)));
    expect([...s.apart].sort()).toEqual([...apart].sort());
  });

  it('draws mutate as the ontology edges list it at 058c5d2, with approval', () => {
    // Hand-read from the edges block of schemas/capability_ontology.yaml.
    const s = safetySequence(cap('mutate'));
    expect(s.before).toEqual([
      { id: 'plan', types: ['precedes'] },
      { id: 'checkpoint', types: ['requires', 'precedes'] },
      { id: 'constrain', types: ['soft_requires', 'precedes'] },
    ]);
    expect(s.after).toEqual([{ id: 'verify', types: ['precedes'] }]);
    expect(s.apart).toEqual(['rollback']);
    expect(s.approval).toBe(true);
    expect(sequenceIsFigure(s)).toBe(true);
  });

  it('prints a sentence, not a figure, for a capability with one rule or none', () => {
    const { text, source } = currentStandardText();
    const rules = edgeRules(text, source);
    // classify: one precedes edge from detect; measure: no ordering edge (hand-read).
    expect(sequenceIsFigure(safetySequence(cap('classify')))).toBe(false);
    expect(sequenceCaption(cap('classify'), safetySequence(cap('classify')), rules)).toBe('In a workflow, detect, where the workflow has it, must come first (V102).');
    expect(sequenceCaption(cap('measure'), safetySequence(cap('measure')), rules)).toMatch(/^No ordering edge/);
  });
});

describe('outputFields (F-C6)', () => {
  /** Top-level keys of the first yaml fence under "## Output Contract", by a line scan. */
  const fenceKeys = (id: string) => {
    const lines = sectionLines(repoText(`skills/${id}/SKILL.md`), /^## Output Contract\s*$/);
    const start = lines.findIndex((l) => l.startsWith('```'));
    const end = lines.findIndex((l, i) => i > start && l.startsWith('```'));
    return [...new Set(lines.slice(start + 1, end).flatMap((l) => /^([a-z_]+):/.exec(l)?.[1] ?? []))];
  };

  it.each(o.capabilities.map((c) => c.id))('%s: the fence\'s fields, and contract fields in + missing = the contract figure\'s outputs', (id) => {
    const f = outputFields(cap(id), repoText(`skills/${id}/SKILL.md`), id);
    expect(f.skill.map((x) => x.name)).toEqual(fenceKeys(id));
    expect(f.skill.filter((x) => x.inContract).length + f.missing.length).toBe(contractSummary(cap(id)).outputCount);
  });

  it('splits mutate\'s nine fields as its fence and the ontology give them', () => {
    // Hand-read from skills/mutate/SKILL.md and mutate's output_schema.
    const f = outputFields(cap('mutate'), repoText('skills/mutate/SKILL.md'), 'mutate');
    expect(f.skill.filter((x) => x.inContract).map((x) => x.name)).toEqual(['success', 'previous_state', 'new_state', 'evidence_anchors']);
    expect(f.skill.filter((x) => !x.inContract).map((x) => x.name)).toEqual(['target', 'operation', 'diff', 'checkpoint_id', 'rollback_command']);
    expect(f.missing).toEqual([]);
    expect(outputFieldsCaption(cap('mutate'), f)).toBe("The skill returns 9 fields: 4 are in mutate's output contract (2 required) and 5 are the skill's own, outside the contract.");
  });

  it('prints a sentence when every field of the fence is in the contract and none is missing', () => {
    const f = { skill: [{ name: 'a', inContract: true, required: true }], missing: [] };
    expect(outputFieldsIsFigure(f)).toBe(false);
  });
});

describe('procedureMap (F-C7)', () => {
  // A hand-written skill: two inputs, three output fields, three steps.
  // Expected values are read off the text by hand.
  const SKILL = [
    '## Inputs',
    '',
    '| Parameter | Required | Type | Description |',
    '|---|---|---|---|',
    '| `target` | Yes | string | What to read |',
    '| `limit` | No | integer | How many |',
    '',
    '## Procedure',
    '',
    '1) **Resolve target**: find `target`',
    '   - Respect limit when given',
    '',
    '2) **Read it**: no field named here (limits and targets are other words)',
    '',
    '3) **Return**: fill `result` and evidence_anchors',
    '',
    '## Output Contract',
    '',
    '```yaml',
    'result: object',
    'evidence_anchors: array',
    'confidence: number',
    '```',
    '',
  ].join('\n');

  it('lists, per step, the inputs and output fields its text names as whole words', () => {
    const m = procedureMap(SKILL, 'fixture');
    expect(m.inputs).toEqual(['target', 'limit']);
    expect(m.outputs).toEqual(['result', 'evidence_anchors', 'confidence']);
    expect(m.steps).toEqual([
      { n: 1, title: 'Resolve target', reads: ['target', 'limit'], writes: [] },
      { n: 2, title: 'Read it', reads: [], writes: [] },
      { n: 3, title: 'Return', reads: [], writes: ['result', 'evidence_anchors'] },
    ]);
  });

  it('is a figure when two steps name a field, and says which output fields no step names', () => {
    const m = procedureMap(SKILL, 'fixture');
    expect(procedureMapIsFigure(m)).toBe(true);
    expect(procedureMapCaption(cap('retrieve'), m)).toBe(
      "2 of the procedure's 3 steps use the name of an input or output field of the retrieve skill as a word; 1 output field of 3 is used by no step (confidence).",
    );
  });

  it('matches a field name that ends a line followed by a sub-item', () => {
    // mdast's toString joins a paragraph and its sub-list with no space, so
    // "covers the target" + "STOP if" read as "targetSTOP"; the step still names target.
    const text = SKILL.replace('2) **Read it**: no field named here (limits and targets are other words)', '2) **Read it**: check the checkpoint covers the target\n   - STOP if not')
      .replace('3) **Return**: fill `result` and evidence_anchors', '3) **Return**: fill result\n   - STOP on error');
    const m = procedureMap(text, 'fixture');
    expect(m.steps[1]!.reads).toEqual(['target']);
    expect(m.steps[2]!.writes).toEqual(['result']);
  });

  it('counts a field named with spaces for underscores, in any case', () => {
    // Audit's step 3 is titled "Extract decision rationale"; its field is decision_rationale.
    const text = SKILL.replace('2) **Read it**: no field named here (limits and targets are other words)', '2) **Collect Evidence anchors**: one per claim');
    const m = procedureMap(text, 'fixture');
    expect(m.steps[1]!.writes).toEqual(['evidence_anchors']);
    // A longer name that only contains the words is not a match.
    const longer = SKILL.replace('2) **Read it**: no field named here (limits and targets are other words)', '2) **Read it**: list the evidence anchorsets');
    expect(procedureMap(longer, 'fixture').steps[1]!.writes).toEqual([]);
  });

  it('falls back to a sentence when fewer than two steps name a field', () => {
    const one = SKILL.replace('fill `result` and evidence_anchors', 'finish');
    const m = procedureMap(one, 'fixture');
    expect(procedureMapIsFigure(m)).toBe(false);
    expect(procedureMapCaption(cap('retrieve'), m)).toBe("1 of the procedure's 3 steps uses the name of an input or output field of the retrieve skill as a word.");
  });
});

describe('chainCaption', () => {
  // spec/EDGE_TYPES.md: for requires, "the 'from' capability MUST be
  // satisfied before 'to' can execute". The ontology's edge is
  // checkpoint -> mutate, so the caption must say checkpoint runs first,
  // never that checkpoint requires mutate.
  it('reads an edge from its source to its target', () => {
    const cap = loadOntology().capabilities.find((c) => c.id === 'mutate')!;
    const text = chainCaption(cap, { follows: ['checkpoint'], precedes: [] });
    expect(text).toContain("the tile's capability must run before mutate");
    expect(text).not.toContain("the tile's capability requires mutate");
  });
});
