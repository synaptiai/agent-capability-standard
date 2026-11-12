// The data behind the domain page figures (visual spec 3.5) and the domains
// index (3.6). Expected values come from line scans of the profile files and
// the domain READMEs, from the ladder rule as the spec words it (applied here
// by hand, not through the code under test), or from hand-written fixtures.
import { describe, expect, it } from 'vitest';
import { loadProfiles } from '../src/data/profiles';
import {
  approvalLadder,
  checkpointCaption,
  checkpointHeader,
  checkpointPolicy,
  complianceRows,
  headingWorkflowId,
  ladderOutcome,
  rankedSources,
  splitReadme,
  thresholdsSentence,
  trustAxis,
} from '../src/lib/domain-figures';
import { profileFiles, profileWorkflowIds, repoText } from './independent';

/** The indented `key: value` lines under a top-level block of a profile file. */
function block(text: string, name: string): [string, string][] {
  const lines = text.split('\n');
  const start = lines.indexOf(`${name}:`);
  if (start === -1) return [];
  const out: [string, string][] = [];
  for (const l of lines.slice(start + 1)) {
    if (/^\S/.test(l)) break;
    const m = /^ {2}([a-z_]+):\s*([^#\s]+)/.exec(l);
    if (m) out.push([m[1]!, m[2]!]);
  }
  return out;
}

// The F-D2 rule in the spec's words: low < medium < high (< critical); human
// if require_human <= L, else review if require_review <= L, else auto if
// auto_approve is not none and L <= auto_approve, else not covered.
const ORDER = ['low', 'medium', 'high', 'critical'];
function specRule(t: Record<string, string>, level: string): string {
  const r = (v: string | undefined) => (v === undefined ? -1 : ORDER.indexOf(v));
  const L = ORDER.indexOf(level);
  if (t.require_human !== undefined && r(t.require_human) <= L) return 'human';
  if (t.require_review !== undefined && r(t.require_review) <= L) return 'review';
  if (t.auto_approve !== undefined && t.auto_approve !== 'none' && L <= r(t.auto_approve)) return 'auto';
  return 'gap';
}

const pageKey = (file: string) => file.replace(/\.yaml$/, '').replaceAll('_', '-');

describe('approval ladder (F-D2)', () => {
  it('gives each profile the outcomes the spec rule gives for its scanned thresholds', () => {
    const files = profileFiles();
    expect(files.length).toBe(loadProfiles().length);
    for (const f of files) {
      const t = Object.fromEntries(block(repoText(`schemas/profiles/${f}`), 'risk_thresholds'));
      const p = loadProfiles().find((x) => x.key === pageKey(f))!;
      const ladder = approvalLadder(p.profile)!;
      expect(ladder.rows.map((r) => r.outcome), f).toEqual(['low', 'medium', 'high'].map((l) => specRule(t, l)));
    }
  });

  it('draws healthcare as human at every level with four capabilities blocked (spec 5.1)', () => {
    const text = repoText('schemas/profiles/healthcare.yaml');
    const blocked = [.../block_autonomous:\n((?:\s+- .*\n)+)/.exec(text)![1]!.matchAll(/-\s*(\w+)/g)].map((m) => m[1]);
    const ladder = approvalLadder(loadProfiles().find((p) => p.key === 'healthcare')!.profile)!;
    expect(ladder.rows.map((r) => r.outcome)).toEqual(['human', 'human', 'human']);
    expect(ladder.blocked).toEqual(blocked);
  });

  it('leaves a level no threshold covers as a gap, and ranks critical above high (fixture)', () => {
    const t = { auto_approve: 'none', require_review: 'high', require_human: 'critical' };
    expect(['low', 'medium', 'high'].map((l) => ladderOutcome(t, l as 'low'))).toEqual(['gap', 'gap', 'review']);
    expect(ladderOutcome({ auto_approve: 'medium', require_review: 'high' }, 'medium')).toBe('auto');
    expect(ladderOutcome({ auto_approve: 'high', require_review: 'medium' }, 'medium')).toBe('review');
  });
});

describe('checkpoint policy (F-D3)', () => {
  it('counts the triggers at each level as the profile file lists them, in schema order', () => {
    for (const f of profileFiles()) {
      const rows = block(repoText(`schemas/profiles/${f}`), 'checkpoint_policy');
      const p = checkpointPolicy(loadProfiles().find((x) => x.key === pageKey(f))!.profile)!;
      expect(p.triggers.map((t) => [t.name, t.level]), f).toEqual(rows);
      const want = ['always', 'high_risk', 'medium_risk', 'never']
        .map((level) => ({ level, count: rows.filter(([, v]) => v === level).length }))
        .filter((x) => x.count > 0);
      expect(p.levels, f).toEqual(want);
    }
  });

  it('uses the one-level header only when every trigger shares a level (the 1.1.5 fallback)', () => {
    for (const f of profileFiles()) {
      const rows = block(repoText(`schemas/profiles/${f}`), 'checkpoint_policy');
      const levels = new Set(rows.map(([, v]) => v));
      const p = checkpointPolicy(loadProfiles().find((x) => x.key === pageKey(f))!.profile)!;
      expect(checkpointHeader(p), f).toBe(levels.size === 1 ? `All ${rows.length} triggers: ${[...levels][0]}` : null);
    }
    // Manufacturing has three levels at 824eea1 (spec 3.5): 4 always, 1 high_risk, 1 medium_risk.
    const m = checkpointPolicy(loadProfiles().find((x) => x.key === 'manufacturing')!.profile)!;
    expect(checkpointCaption(m)).toBe('6 triggers: 4 always, 1 high risk and 1 medium risk.');
  });
});

describe('domain sources (F-D5) and compliance (F-D7)', () => {
  it('ranks sources by default trust, highest first, keeping file order on ties', () => {
    for (const f of profileFiles()) {
      const text = repoText(`schemas/profiles/${f}`);
      const scanned = [...text.matchAll(/- name: (.+)\n\s+type: (\w+)\n\s+default_trust: ([\d.]+)/g)].map((m) => ({ name: m[1]!.trim(), type: m[2]!, trust: Number(m[3]) }));
      const want = scanned.map((s, i) => ({ s, i })).sort((a, b) => b.s.trust - a.s.trust || a.i - b.i).map((x) => x.s);
      expect(rankedSources(loadProfiles().find((x) => x.key === pageKey(f))!.profile), f).toEqual(want);
    }
  });

  it('reads retention days as years to one decimal (2555 days is about 7.0 years, spec 3.5)', () => {
    const rows = complianceRows({ compliance: { hipaa: 'required', audit_retention_days: 2555, other: 'something_else' } })!;
    expect(rows).toEqual([
      { key: 'hipaa', value: 'required', glyph: 'stamp' },
      { key: 'audit_retention_days', value: '2555 days', glyph: null, years: 7 },
      { key: 'other', value: 'something else', glyph: null },
    ]);
    expect(complianceRows({})).toBeNull();
  });
});

describe('README placement (F-D6 and the Domain Profile <details>)', () => {
  it('finds both anchors in every domain README and an H3 for every workflow its profile lists', () => {
    for (const f of profileFiles()) {
      const readme = repoText(`docs/domains/${pageKey(f)}/README.md`);
      expect(readme, f).toMatch(/^## Domain Profile$/m);
      expect(readme, f).toMatch(/^## Available Workflows$/m);
      const section = readme.split(/^## Available Workflows$/m)[1]!.split(/^## /m)[0]!;
      // The H3 title with its number removed, lower case, other characters as `_` (spec 3.5, F-D6).
      const h3 = [...section.matchAll(/^### (?:\d+\.\s*)?(.+)$/gm)].map((m) => m[1]!.toLowerCase().replace(/[^a-z0-9]+/g, '_'));
      for (const id of profileWorkflowIds(repoText(`schemas/profiles/${f}`))) expect(h3, `${f} ${id}`).toContain(id);
    }
  });

  it('turns a README heading into its workflow id', () => {
    expect(headingWorkflowId('1. Patient Monitoring')).toBe('patient_monitoring');
    expect(headingWorkflowId('3. Text-to-Image Generation')).toBe('text_to_image_generation');
    expect(headingWorkflowId('4. Cross-modal Search')).toBe('cross_modal_search');
  });

  it('splits the README around the profile section and after each matched workflow heading (fixture)', () => {
    const html = [
      '<h2 id="overview">Overview</h2><p>o</p>',
      '<h2 id="domain-profile">Domain Profile<a href="#domain-profile"></a></h2><h3 id="trust-weights">Trust Weights</h3><p>t</p>',
      '<h2 id="available-workflows">Available Workflows</h2>',
      '<h3 id="1-alpha-run">1. Alpha Run<a></a></h3><p>a</p>',
      '<h3 id="2-beta">2. Beta</h3><p>b</p>',
      '<h2 id="later">Later</h2><h3 id="1-alpha-run-1">1. Alpha Run</h3>',
    ].join('');
    const parts = splitReadme(html, ['alpha_run', 'gamma']);
    expect(parts.before).toBe('<h2 id="overview">Overview</h2><p>o</p>');
    expect(parts.profileHeading).toBe('<h2 id="domain-profile">Domain Profile<a href="#domain-profile"></a></h2>');
    expect(parts.profileBody).toBe('<h4 id="trust-weights">Trust Weights</h4><p>t</p>');
    expect(parts.segments.map((s) => s.after)).toEqual(['alpha_run', null]);
    expect(parts.segments[0]!.html.endsWith('1. Alpha Run<a></a></h3>')).toBe(true);
    expect(parts.segments.map((s) => s.html).join('')).toBe(html.slice(html.indexOf('<h2 id="available-workflows">')));
    expect(parts.unplaced).toEqual(['gamma']);
  });

  it('keeps everything as one segment when the README has neither anchor (fixture)', () => {
    const parts = splitReadme('<h2 id="x">X</h2><p>x</p>', ['a']);
    expect(parts).toEqual({ before: '', profileHeading: null, profileBody: null, segments: [{ html: '<h2 id="x">X</h2><p>x</p>', after: null }], unplaced: ['a'] });
  });
});

describe('domains index (3.6)', () => {
  it('puts the dot-strip axis at the floor and ceiling, to 0.05, of every scanned trust weight', () => {
    const all = profileFiles().flatMap((f) => block(repoText(`schemas/profiles/${f}`), 'trust_weights').map(([, v]) => Number(v)));
    expect(all.length).toBeGreaterThan(0);
    const { min, max } = trustAxis(loadProfiles());
    expect(min).toBeCloseTo(Math.floor(Math.min(...all) / 0.05 + 1e-9) * 0.05, 9);
    expect(max).toBeCloseTo(Math.ceil(Math.max(...all) / 0.05 - 1e-9) * 0.05, 9);
  });

  it('groups the profiles by their low, medium and high outcomes', () => {
    const outcomes = profileFiles().map((f) => {
      const t = Object.fromEntries(block(repoText(`schemas/profiles/${f}`), 'risk_thresholds'));
      return { key: pageKey(f), o: ['low', 'medium', 'high'].map((l) => specRule(t, l)) };
    });
    const sentence = thresholdsSentence(loadProfiles());
    const common = outcomes.filter((x) => x.o.join() === 'auto,review,human');
    expect(common.length).toBeGreaterThan(1);
    expect(sentence).toContain(`${common.length} profiles go auto, review, human`);
    for (const x of outcomes.filter((y) => y.o.every((v) => v === 'human'))) expect(sentence).toContain(`${x.key} is human at every level`);
  });
});
