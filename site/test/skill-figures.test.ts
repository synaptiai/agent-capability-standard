// Tests on the figures a composed skill's page draws from data
// (src/lib/skill-figures.ts). Expected values come from line scans of the
// SKILL.md files, the PVC checklist and the workflow catalog
// (test/independent.ts), never from the functions under test.
import { describe, expect, it } from 'vitest';
import { COMPOSED_SKILLS } from '../src/data/skills';
import { loadWorkflows } from '../src/data/workflows';
import {
  checkSteps,
  checkStepsIsFigure,
  composedSkillFigures,
  exampleMatches,
  guardedSteps,
  scorecard,
  SKILL_HEADINGS,
} from '../src/lib/skill-figures';
import { catalogSteps, repoText } from './independent';

const SOURCE = (dir: string) => `skills/${dir}/SKILL.md`;
const text = (dir: string) => repoText(SOURCE(dir));

/** The H2 ids GitHub gives a SKILL.md's headings, by a line scan. */
function h2Ids(dir: string): string[] {
  return text(dir)
    .split('\n')
    .flatMap((l) => /^## (.+)$/.exec(l)?.[1] ?? [])
    .map((h) => h.toLowerCase().replace(/[^a-z0-9 -]/g, '').replace(/ /g, '-'));
}

describe('composed skill figures', () => {
  it('places every figure under an H2 the skill has, and knows that H2 by its text', () => {
    for (const dir of Object.keys(COMPOSED_SKILLS)) {
      const figs = composedSkillFigures(dir, text(dir), SOURCE(dir));
      for (const key of Object.keys(figs)) {
        expect(h2Ids(dir), `${dir}: ${key}`).toContain(key);
        expect(SKILL_HEADINGS[key], key).toBeDefined();
      }
      expect(Object.keys(figs).length, dir).toBeGreaterThan(0);
    }
  });

  it('gives a skill that runs a workflow its step map, drawn from that workflow', () => {
    for (const [dir, wfId] of Object.entries(COMPOSED_SKILLS)) {
      if (wfId === null) continue;
      const spine = composedSkillFigures(dir, text(dir), SOURCE(dir)).procedure?.[0];
      expect(spine?.kind, dir).toBe('spine');
      const wf = spine && 'wf' in spine ? spine.wf : undefined;
      // The step count from a scan of the catalog file the workflow is in.
      const steps = catalogSteps(loadWorkflows().byId.get(wfId)!.source).get(wfId)!;
      expect(wf?.steps.map((s) => s.capability), dir).toEqual(steps);
    }
  });

  it('lists the guarded steps of the sync loop: those with gates, a condition, a checkpoint need or approval', () => {
    const wf = loadWorkflows().byId.get('digital_twin_sync_loop')!;
    const g = guardedSteps(wf);
    // From the skill's own text: steps 1, 16, 17, 18 and 19 have gates (the
    // procedure and the preconditions name them), step 16 (mutate) runs only
    // when the plan is compliant, and mutate and execute need approval.
    const lines = repoText(wf.source).split('\n');
    const start = lines.findIndex((l) => l === 'digital_twin_sync_loop:');
    const end = lines.findIndex((l, i) => i > start && /^[A-Za-z_]/.test(l));
    let step = 0;
    const gated = new Set<number>();
    for (const l of lines.slice(start, end)) {
      if (/^\s*- capability: /.test(l)) step += 1;
      // `gates: []` is an empty list: no gates.
      if (/^\s+gates:\s*$/.test(l)) gated.add(step);
    }
    expect(g.filter((s) => s.gates.length > 0).map((s) => s.index)).toEqual([...gated]);
    expect(g.filter((s) => s.condition !== null).map((s) => s.capability)).toEqual(['mutate']);
    expect(g.filter((s) => s.approval).map((s) => s.capability)).toEqual(['mutate', 'execute']);
  });

  it('matches verification checks to the steps whose stored output they name', () => {
    const wf = loadWorkflows().byId.get('capability_gap_analysis')!;
    const c = checkSteps(wf, text('capability-gap-analysis'));
    // Checkbox lines under "## Verification", by a line scan.
    const items = text('capability-gap-analysis').split('## Verification')[1]!.split('\n## ')[0]!.split('\n').filter((l) => /^- \[ \]/.test(l));
    expect(c.checks.length).toBe(items.length);
    // "Relationships Mapped" names attribute_out and discover_out.
    const rel = c.checks.find((k) => k.title === 'Relationships Mapped')!;
    expect(rel.steps.map((k) => wf.steps[k - 1]!.store_as)).toEqual(['attribute_out', 'discover_out']);
    expect(checkStepsIsFigure(c)).toBe(true);
  });
});

describe('checkSteps past a fenced heading', () => {
  it('reads the checks after a "## " line inside a fence in the Verification section', () => {
    const wf = loadWorkflows().byId.get('capability_gap_analysis')!;
    const text = ['## Verification', '', '```markdown', '## Not a section', '```', '', '- [ ] **First**: one', '- [ ] **Second**: two', '', '## Next'].join('\n');
    expect(checkSteps(wf, text).checks.map((c) => c.title)).toEqual(['First', 'Second']);
  });
});

describe('the scorecard figure', () => {
  it('groups the contract scorecard ids by the checklist families, all of them, in checklist order', () => {
    const sc = scorecard('perspective-validation', text('perspective-validation'), SOURCE('perspective-validation'))!;
    const checklist = repoText('skills/perspective-validation/CHECKLIST.md').split('\n');
    const families = checklist.flatMap((l) => /^### ([A-Z])\) /.exec(l)?.[1] ?? []);
    const ids = checklist.flatMap((l) => /^#### ([A-Z]+-\d+) /.exec(l)?.[1] ?? []);
    expect(sc.families.map((f) => f.letter)).toEqual(families);
    expect(sc.families.flatMap((f) => f.checks.map((c) => c.id))).toEqual(ids);
    // The scorecard keys in the Output Contract fence, by a line scan.
    const contract = text('perspective-validation').split('## Output Contract')[1]!.split('\n## ')[0]!;
    const keys = contract.split('\n').flatMap((l) => /^ {2}([A-Z]+-\d+): /.exec(l)?.[1] ?? []);
    expect([...keys].sort()).toEqual([...ids].sort());
    expect(sc.ratings).toEqual(['PASS', 'PARTIAL', 'FAIL', 'N/A']);
  });

  it('is absent for a skill without a checklist', () => {
    expect(scorecard('discover-capabilities', text('discover-capabilities'), SOURCE('discover-capabilities'))).toBeNull();
  });
});

describe('the example matches figure', () => {
  it('reads every capability each discover-capabilities example output lists, and the auto-added ones', () => {
    const m = exampleMatches(text('discover-capabilities'), SOURCE('discover-capabilities'));
    const lines = text('discover-capabilities').split('\n## Examples')[1]!.split('\n## ')[0]!.split('\n');
    // "  - id: x" lines under "capabilities:" in the examples, and "Auto-added" reasonings.
    const ids = lines.filter((l) => /^ {2}- id: /.test(l)).map((l) => l.replace(/^ {2}- id: /, '').trim());
    const auto = lines.filter((l) => /reasoning: "Auto-added/.test(l)).length;
    expect(m.examples.flatMap((e) => e.matches.map((x) => x.id))).toEqual(ids);
    expect(m.examples.flatMap((e) => e.matches).filter((x) => x.auto).length).toBe(auto);
  });
});

describe('the Markdown copy of a composed skill page', () => {
  it('has one figure block for each figure the page draws', async () => {
    const { ROUTES } = await import('../src/lib/routes');
    const { skillFigureEdits } = await import('../src/twins/skills');
    const { parseMarkdown, stripFrontmatter } = await import('../src/lib/anchors');
    for (const dir of Object.keys(COMPOSED_SKILLS)) {
      expect(ROUTES.some((r) => r.source === SOURCE(dir)), dir).toBe(true);
      const figs = Object.values(composedSkillFigures(dir, text(dir), SOURCE(dir))).flat();
      const drawn = figs.filter((f) => f.kind !== 'sentence').length;
      const body = stripFrontmatter(text(dir)).replace(/^\s+/, '');
      const inserted = skillFigureEdits(dir, SOURCE(dir))(parseMarkdown(body)).map((e) => e.text).join('');
      expect((inserted.match(/\*\*Figure: /g) ?? []).length, dir).toBe(drawn);
    }
  });
});
