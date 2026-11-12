// Text equivalents, in a composed skill's Markdown copy, of the figures its
// page draws from data (src/lib/skill-figures.ts). Each block goes directly
// under the H2 the page draws its figure under, with the same title and
// caption, so the copy reads in the page's order.
import type { Heading, Root } from 'mdast';
import { headingText } from '../lib/anchors';
import { procedureMapCaption, procedureMapTitle } from '../lib/capability-figures';
import { readRepoFile } from '../lib/repo';
import {
  checkStepsCaption,
  checkStepsTitle,
  composedSkillFigures,
  guardedStepsCaption,
  guardedStepsTitle,
  exampleMatchesCaption,
  exampleMatchesTitle,
  scorecardCaption,
  scorecardTitle,
  SKILL_HEADINGS,
  type SkillFigure,
} from '../lib/skill-figures';
import { dataFlowGrid, readsList, riskSummary, spineTable, workflowSpine } from '../lib/workflow-figures';
import { cell, code, figure, mdLink, table } from './md';

/** The Markdown block for one figure of a composed skill's page. */
export function skillFigureBlock(dir: string, f: SkillFigure): string {
  switch (f.kind) {
    case 'spine': {
      const spine = workflowSpine(f.wf);
      const map = spineTable(spine);
      return figure(
        spine.title,
        `${spine.caption} Each step's card is on the ${mdLink(code(f.wf.id), `/workflows/${f.wf.slug}/`)} page.`,
        table(map.headers, map.rows.map((r) => r.map((c, i) => (i === 1 && c ? code(c) : cell(c))))),
      );
    }
    case 'flow': {
      const flow = dataFlowGrid(f.wf);
      return figure(flow.title, flow.caption, readsList(workflowSpine(f.wf)).map((l) => `- ${l}`).join('\n') || 'No step reads an earlier output.');
    }
    case 'risk': {
      const r = riskSummary(f.wf);
      return figure(r.title, r.caption, r.steps.map((s) => `- Step ${s.index} (${code(s.capability)}): ${s.risk}`).join('\n'));
    }
    case 'sentence':
      return f.text;
    case 'procedure':
      return figure(
        procedureMapTitle({ id: dir }),
        procedureMapCaption({ id: dir }, f.map),
        table(
          ['Step', 'Inputs it uses by name', 'Output fields it uses by name'],
          f.map.steps.map((s) => [`${s.n}. ${cell(s.title)}`, s.reads.map(code).join(', '), s.writes.map(code).join(', ')]),
        ),
      );
    case 'examples':
      return figure(
        exampleMatchesTitle(dir),
        exampleMatchesCaption(f.matches),
        table(
          ['Example', 'Capability', 'Confidence', 'Added for safety'],
          f.matches.examples.flatMap((e) =>
            e.matches.map((m) => [`${e.n}. ${cell(e.title)}`, `${code(m.id)}${m.domain ? ` (${m.domain})` : ''}`, String(m.confidence), m.auto ? 'Yes' : 'No']),
          ),
        ),
      );
    case 'guards':
      return figure(
        guardedStepsTitle(f.wf),
        guardedStepsCaption(f.wf, f.steps),
        table(
          ['Step', 'Needs', 'Runs only when', 'Gates'],
          f.steps.map((s) => [
            `${s.index}. ${code(s.capability)}`,
            [s.checkpoint && 'a checkpoint first', s.approval && 'approval'].filter(Boolean).join(', '),
            s.condition !== null ? code(s.condition) : '',
            s.gates.map((g) => `${g.action} when ${code(g.when)}`).join('; '),
          ].map(cell)),
        ),
      );
    case 'checks':
      return figure(
        checkStepsTitle(f.wf),
        checkStepsCaption(f.wf, f.checks),
        table(
          ['Check', 'Steps whose output it names'],
          f.checks.checks.map((c) => [`${c.n}. ${cell(c.title)}`, c.steps.map((k) => `${k} (${code(f.wf.steps.find((s) => s.index === k)!.store_as!)})`).join(', ') || 'none']),
        ),
      );
    case 'scorecard':
      return figure(
        scorecardTitle(f.card),
        scorecardCaption(f.card),
        table(
          ['Family', 'Checks'],
          f.card.families.map((fam) => [`${fam.letter}) ${cell(fam.name)} (${fam.code})`, fam.checks.map((c) => `${code(c.id)} ${cell(c.title)}`).join('; ')]),
        ),
      );
  }
}

/** Insertions under each H2 of a composed skill's source that the page draws a figure under. */
export function skillFigureEdits(dir: string, source: string): (tree: Root) => { start: number; end: number; text: string }[] {
  const figs = composedSkillFigures(dir, readRepoFile(source), source);
  return (tree) =>
    Object.entries(figs).map(([key, list]) => {
      const want = SKILL_HEADINGS[key];
      if (!want) throw new Error(`twins: no heading text for the skill figure key ${key}`);
      const h = tree.children.find((n): n is Heading => n.type === 'heading' && n.depth === 2 && headingText(n).trim() === want);
      const end = h?.position?.end.offset;
      if (end === undefined) throw new Error(`twins: ${source} has no "## ${want}" for its figures`);
      return { start: end, end, text: `\n\n${list.map((f) => skillFigureBlock(dir, f)).join('\n\n')}` };
    });
}
