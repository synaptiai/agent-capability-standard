// Text equivalents, in the current Standard's Markdown copy, of the figures
// from §1 to §5.19 that show more than the table, list or fence they sit
// beside (visual spec 3.9 "twin block", 6.1). Each block uses the same
// caption function as the page's <figcaption>; specFigureBlocks() appends
// them, in page order, to its "Figures on this page" section.
import { loadOntology } from '../data/ontology';
import { currentStandardText } from '../lib/spec-figures';
import * as D from '../lib/spec-dsl-figures';
import { exhaustedWords, REPLAY_FIXTURES, replay, replayCaption, replayRows } from '../lib/run-replay';
import { loadWorldStateSchema } from '../data/spec-sources';
import { cell, code, figure, table } from './md';
import { readRepoFile } from '../lib/repo';
import * as T from '../lib/spec-tail-figures';
import { loadIdentityPolicy } from '../data/spec-sources';
import type { SpecSlot } from '../lib/spec-slots';
import { slotBlocks } from './spec-slot-blocks';

const REPLAY_TITLES: Record<string, string> = {
  'group-replay': 'A group member that fails, from §5.2.3',
  'recovery-replay': 'A recovery that runs out, from §5.12',
  'wait-replay': 'A wait that loses its source, from §5.13',
  'approval-unattended-replay': 'An approval no one is asked for, from §5.14',
  'recheck-replay': 'A changed source, asked again, from §5.14',
  'deferral-replay': 'What a deferral reaches, from §5.14',
  'resume-replay': 'What a resumption runs again, from §5.14.1',
  'resume-skip-replay': 'A queued step that no longer runs, from §5.14.1',
  'protocol-replay': "A run's actions and the host's answers, from §5.19.1",
  'wake-replay': "A retry's wait, ended by a tick, from §5.19.3",
  'cancel-replay': 'A run cancelled while its mutation is pending, from §5.19.5',
  'reason-replay': 'An error that says why, retried, from §5.19.7',
  'response-replay': 'Responses with members this version does not define, from §5.19.1',
  'grounding-replay': 'An ungrounded output, sent back for evidence, from §5.20',
  'citation-replay': 'A citation of a value the step does not bind, from §5.20',
  'audit-replay': 'An audit step whose record was not written, from §6.4',
  'secret-replay': 'A persist refused for a secret in its data, from §6.7',
  'export-replay': "A target another catalog does not export, from §5.1.1",
  'family-replay': "Families compared exactly, from §5.15",
  'manifest-replay': "A delegation whose target has no manifest, from §5.15.1",
  'agents-replay': "A delegation that takes its target's flags, from §5.15.2",
  'read-only-replay': "A read-only delegation its host does not attest, from §5.15.2",
  'continue-replay': "A continuation matched by its own task_id, from §5.15.3",
  'rollback-replay': 'A rollback that did not restore everything, stopped, from §4.4.1',
  'not-covered-replay': 'A rollback after a send, the send not covered, from §4.4.1',
  'send-key-replay': 'One approval, one key, across a retry, from §4.4.2',
  'destination-replay': 'A send to a destination no policy allows, from §4.4.2',
  'scope-replay': 'A memory step whose scope the host did not use, from §4.5',
  'stored-replay': 'A persist that stored nothing, completed, from §4.5',
  'delegate-rollback-replay': "A rollback after a delegation, the delegate's change not covered, from §5.15.4",
};

function replayBlock(slot: string): string {
  const r = replay(REPLAY_FIXTURES[slot]!);
  return figure(
    REPLAY_TITLES[slot]!,
    replayCaption(r),
    table(['Step', 'Capability', 'Stored as', 'What happened', 'Why'], replayRows(r).map((row) => [row[0]!, code(row[1]!), row[2] ? code(row[2]) : '', row[3]!, cell(row[4]!)])) +
      (r.loops.length > 0 ? `\n\n${r.loops.map((l) => `Loop ${l.count}${l.maxLoops !== null ? ` of max_loops ${l.maxLoops}` : ''}: from step ${l.from} back to step ${l.to}.`).join('\n')}` : '') +
      (exhaustedWords(r) ? `\n\n${exhaustedWords(r)}.` : '') +
      `\n\nThe run ends ${r.end.code ? `failed, ${r.end.code}` : `${r.end.kind.toLowerCase()}, outcome ${r.end.outcome}`}.`,
  );
}

/** The blocks for §1 to §5.2.3: F-S0, F-S1, F-S6 and the parallel group replay. */
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
        D.safetyDefaults(o).flatMap((g) => g.caps.map((c) => [code(c.id), g.layer, c.risk, yes(c.mutation), D.checkpointViaEdge(c) ? 'Yes, via requires edge' : yes(c.requires_checkpoint), yes(c.requires_approval)])),
      ),
    ),
    replayBlock('export-replay'),
    replayBlock('group-replay'),
  ];
}

/** The blocks for §4.4.1 to §4.5, in page order. */
export function specEffectBlocks(): string[] {
  return ['rollback-replay', 'not-covered-replay', 'send-key-replay', 'destination-replay', 'scope-replay', 'stored-replay'].map(replayBlock);
}

/** The blocks for §5.9 to §5.19, in page order. */
export function specLateBlocks(): string[] {
  const { source, text } = currentStandardText();
  const ext = D.extensionTiles(text, source);
  const plans = D.approvalPlans(text, source);
  const asked = D.approverAsked(text, source);
  const deleg = D.delegateGroups(text, source);
  const trust = D.trustClassBars(text, source);
  const approvers = D.approverCount(text, source);
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
    replayBlock('approval-unattended-replay'),
    replayBlock('recheck-replay'),
    replayBlock('deferral-replay'),
    replayBlock('resume-replay'),
    replayBlock('resume-skip-replay'),
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
    replayBlock('family-replay'),
    replayBlock('manifest-replay'),
    replayBlock('agents-replay'),
    replayBlock('read-only-replay'),
    replayBlock('continue-replay'),
    replayBlock('delegate-rollback-replay'),
    figure(
      'Trust classes, from §5.17',
      D.trustCaption(trust),
      table(['Trust class', 'Default weight', 'In the example'], trust.map((b) => [code(b.cls), String(b.weight), [b.accepted ? 'accepted' : '', b.alwaysAsk ? 'always ask' : ''].filter(Boolean).join(', ')])),
    ),
    figure(
      'Who counts as an approver, from §5.17',
      D.approverCaption(approvers),
      table(['Approver', 'Kind', 'Role', 'Counts', 'Why'], approvers.rows.map((r) => [code(r.principal), r.kind, r.role ?? '', r.counts ? 'Yes' : 'No', cell(r.why)])),
    ),
    replayBlock('protocol-replay'),
    replayBlock('response-replay'),
    replayBlock('wake-replay'),
    replayBlock('cancel-replay'),
    replayBlock('reason-replay'),
    replayBlock('grounding-replay'),
    replayBlock('citation-replay'),
  ];
}

/** The blocks for chapters 7 to 10: F-S24b, F-S25, F-S26, F-S27 and F-S29. */
export function specTailBlocks(): string[] {
  const { source, text } = currentStandardText();
  const decay = T.decayColumns(text, source);
  const fams = T.diagnosticFamilies(text, source);
  const heat = T.codeHeat(text, source);
  const suite = T.conformanceSuite(text, source);
  const digests = T.digestVectors(text, source);
  const effects = T.effectVectors(text, source);
  return [
    replayBlock('audit-replay'),
    replayBlock('secret-replay'),
    figure(
      'Merge thresholds, from §7.3',
      T.thresholdsCaption(),
      table(['Threshold', 'Score'], loadIdentityPolicy().thresholds.map((t) => [code(t.name), String(t.value)])) +
        '\n\n' +
        table(['Band', 'Action', 'Given by'], [...T.mergeBands()].reverse().map((b) => [`${b.from} to ${b.to}`, b.action ? code(b.action) : 'none named', b.threshold ? `${T.THRESHOLD_ACTIONS[b.threshold]!.side === 'above' ? 'at or above' : 'below'} ${code(b.threshold)}` : ''])),
    ),
    figure(
      'Decay with a floor: reference configuration, from §8.1',
      T.decayCaption(decay),
      table(['Age (half-lives)', 'Age (days)', 'Decay factor', 'Held by the floor'], decay.columns.map((c) => [String(c.halfLives), String(c.days), c.value.toFixed(3), c.floored ? 'Yes' : 'No'])),
    ),
    figure('Diagnostic families, from §9.1', T.familiesCaption(fams), table(['Family', 'Range', 'Severity', 'Codes'], fams.map((f) => [f.name, code(f.range), f.severity, String(f.codes.length)]))),
    figure(
      'Where codes are raised, from §9.6',
      T.heatCaption(heat),
      table(['Section', ...heat.families.map((f) => f.name)], heat.sections.map((x, j) => [`§${x.n} ${x.title}`, ...heat.families.map((_, i) => String(heat.counts[i]![j]))])),
    ),
    figure('The conformance suite, from §10.3', T.suiteCaption(suite), table(['Part', 'Count', 'Folder'], suite.map((p) => [p.label, String(p.count), code(p.dir)]))),
    figure('The approval digest vectors, from §10.3', T.digestCaption(digests), table(['Vectors', 'Count'], digests.map((g) => [g.label, String(g.count)]))),
    figure('The destination and memory vectors, from §10.3', T.effectVectorsCaption(effects), table(['Vectors', 'Count', 'File'], effects.map((g) => [g.label, String(g.count), code(g.source)]))),
  ];
}

/** An older Standard's figure blocks: one per figure its page draws, the keyword counts with their table. */
export function specOlderBlocks(source: string, slots: readonly SpecSlot[]): string[] {
  const chapters = D.chapterKeywords(readRepoFile(source));
  return slotBlocks(slots, source, [
    figure(
      'Where the requirements are, from §1.2',
      D.keywordsCaption(chapters),
      table(['Chapter', ...D.KEYWORD_GROUPS.map((g) => g.label)], chapters.map((c) => [`${c.n}. ${c.title}`, ...D.KEYWORD_GROUPS.map((g) => String(c.counts[g.id]))])),
    ),
  ]);
}
