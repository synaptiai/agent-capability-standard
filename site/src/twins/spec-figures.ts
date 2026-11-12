// Text equivalents, in the current Standard's Markdown copy, of the figures
// from §1 to §5.17 that show more than the table, list or fence they sit
// beside (visual spec 3.9 "twin block", 6.1). Each block uses the same
// caption function as the page's <figcaption>; specFigureBlocks() appends
// them, in page order, to its "Figures on this page" section.
import { loadOntology } from '../data/ontology';
import { currentStandardText } from '../lib/spec-figures';
import * as D from '../lib/spec-dsl-figures';
import { REPLAY_FIXTURES, replay, replayCaption, replayRows } from '../lib/run-replay';
import { loadWorldStateSchema } from '../data/spec-sources';
import { cell, code, figure, table } from './md';

const REPLAY_TITLES: Record<string, string> = {
  'recovery-replay': 'A recovery that runs out, from §5.12',
  'wait-replay': 'A wait that loses its source, from §5.13',
  'deferral-replay': 'What a deferral reaches, from §5.14',
};

function replayBlock(slot: string): string {
  const r = replay(REPLAY_FIXTURES[slot]!);
  return figure(
    REPLAY_TITLES[slot]!,
    replayCaption(r),
    table(['Step', 'Capability', 'Stored as', 'What happened', 'Why'], replayRows(r).map((row) => [row[0]!, code(row[1]!), row[2] ? code(row[2]) : '', row[3]!, cell(row[4]!)])) +
      (r.loops.length > 0 ? `\n\n${r.loops.map((l) => `Loop ${l.count}${l.maxLoops !== null ? ` of max_loops ${l.maxLoops}` : ''}: from step ${l.from} back to step ${l.to}.`).join('\n')}` : '') +
      `\n\nThe run ends ${r.end.code ? `failed, ${r.end.code}` : `${r.end.kind.toLowerCase()}, outcome ${r.end.outcome}`}.`,
  );
}

/** The blocks for §1 to §5.2.1: F-S0, F-S1 and F-S6. */
export function specEarlyBlocks(): string[] {
  const { text } = currentStandardText();
  const o = loadOntology();
  const chapters = D.chapterKeywords(text);
  const order = D.safetyOrder(o);
  const yes = (b: boolean) => (b ? 'Yes' : 'No');
  return [
    figure(
      'Where the requirements are, from §1.2',
      D.keywordsCaption(chapters),
      table(['Chapter', ...D.KEYWORD_GROUPS.map((g) => g.label)], chapters.map((c) => [`${c.n}. ${c.title}`, ...D.KEYWORD_GROUPS.map((g) => String(c.counts[g.id]))])),
    ),
    figure(
      'Safety ordering, from §3.3',
      D.safetyOrderCaption(order),
      table(['From', 'Edge', 'To'], order.flatMap((g) => g.edges.map((e) => [code(g.source), code(e.type), e.targets.map(code).join(', ')]))),
    ),
    figure(
      'Safety defaults by capability, from §5.2.1',
      D.safetyDefaultsCaption(o),
      table(
        ['Capability', 'Layer', 'Risk', 'Changes state', 'Needs checkpoint', 'Needs approval'],
        D.safetyDefaults(o).flatMap((g) => g.caps.map((c) => [code(c.id), g.layer, c.risk, yes(c.mutation), yes(c.requires_checkpoint), yes(c.requires_approval)])),
      ),
    ),
  ];
}

/** The blocks for §5.9 to §5.17, in page order. */
export function specLateBlocks(): string[] {
  const { source, text } = currentStandardText();
  const ext = D.extensionTiles(text, source);
  const plans = D.approvalPlans(text, source);
  const asked = D.approverAsked(text, source);
  const deleg = D.delegateGroups(text, source);
  const trust = D.trustClassBars(text, source);
  return [
    figure('Extensions and what they unlock, from §5.9', D.extensionsCaption(ext), table(['Extension', 'Sections'], ext.map((e) => [code(e.id), e.sections.map((s) => `§${s}`).join(', ')]))),
    replayBlock('recovery-replay'),
    replayBlock('wait-replay'),
    figure(
      'Who decides, and what then, from §5.14',
      D.approvalCaption(plans),
      [
        table(['Approver kind', 'Attended run', 'Unattended run'], asked.map((a) => [code(a.kind), a.attended ? 'asked' : 'not asked', a.unattended ? 'asked' : 'not asked'])),
        `Decisions: ${loadWorldStateSchema().approvalDecisions.map(code).join(', ')}.`,
        table(['when_unattended', 'Result'], plans.map((p) => [`${code(p.plan)}${p.isDefault ? ' (default)' : ''}`, cell(p.result)])),
      ].join('\n\n'),
    ),
    replayBlock('deferral-replay'),
    figure(
      'What a delegate binds, from §5.15',
      D.delegateCaption(deleg),
      table(
        ['Field', 'Side', 'Type', 'Needs'],
        [
          ...deleg.inputs.flatMap((g) => g.rows.map((r) => [code(r.name), 'input', code(r.type), g.extension ? code(g.extension) : 'nothing'])),
          ...deleg.outputs.map((r) => [code(r.path), 'output', code(r.type), '']),
        ],
      ),
    ),
    figure(
      'Trust classes, from §5.17',
      D.trustCaption(trust),
      table(['Trust class', 'Default weight', 'In the example'], trust.map((b) => [code(b.cls), String(b.weight), [b.accepted ? 'accepted' : '', b.alwaysAsk ? 'always ask' : ''].filter(Boolean).join(', ')])),
    ),
  ];
}
