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
  neighbourCounts,
  neighbourhoodCaption,
  neighbours,
  relationWords,
  splitAtH2s,
} from '../src/lib/capability-figures';
import { ontologyEdgeTriples, repoText, symmetricEdgeTypes } from './independent';

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
    // Visual spec 6.1 gives this sentence word for word.
    expect(neighbourhoodCaption(cap('mutate'), got)).toBe(
      'mutate has 12 relationships with 8 capabilities: 8 point into it, 3 point out of it, and 1 runs both ways.',
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
