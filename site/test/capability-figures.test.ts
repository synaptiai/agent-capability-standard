// Tests on what the capability page's figures show (visual spec 3.1, 6.3).
// Expected values come from line scans of the ontology and the SKILL.md
// files (test/independent.ts), from the spec's own reading of mutate at
// 824eea1 (a hand-written fixture), or from the spec's caption wording;
// never from the functions under test.
import { describe, expect, it } from 'vitest';
import { loadOntology } from '../src/data/ontology';
import {
  compositionChain,
  contractRowId,
  contractSummary,
  edgeRules,
  outputFields,
  outputFieldsCaption,
  outputFieldsIsFigure,
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

describe('compositionChain', () => {
  /** A scan: for each "- " item under a label in Composition Patterns, its first backticked word that is a capability id. */
  function scan(text: string, label: string): string[] {
    const sec = text.split(/^## Composition Patterns\s*$/m)[1]?.split(/^## /m)[0] ?? '';
    const block = sec.split(`**${label}:**`)[1]?.split(/\n\s*\n/)[0] ?? '';
    const ids = block
      .split('\n')
      .filter((l) => l.startsWith('- '))
      .flatMap((l) => [...l.matchAll(/`([a-z_]+)`/g)].map((m) => m[1]!).filter((x) => o.byId.has(x)).slice(0, 1));
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
