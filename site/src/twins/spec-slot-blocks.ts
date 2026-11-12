// Every site-drawn figure of a Standard page gets a block in the page's
// Markdown copy, in page order (visual spec 6.1: the information of a figure
// is also in the Markdown copy). A figure that shows data its section's own
// table does not hold has a table of that data (specFigureBlocks and
// friends); every other figure gets its title, its caption (the same
// function the page's <figcaption> calls, so the words agree) and, where
// the figure works something out from its source (an order, a tally, the
// outcomes of a tree), that result as a short table or list.
import { annotationCaption, annotationGrammar, annotationGroups, bindingExamples, failureBranches, failureCaption, referenceCaption } from '../lib/spec-figures';
import type { SpecSlot } from '../lib/spec-slots';
import * as D from '../lib/spec-dsl-figures';
import * as T from '../lib/spec-tail-figures';
import { loadCatalogSchema } from '../data/catalog-schema';
import { readRepoFile } from '../lib/repo';
import { cell, code, figure, table } from './md';

/** The figure's title as the page prints it: "{name}, from §{n}". */
export function slotTitle(slot: SpecSlot, text: string, where: string): string {
  const name = SLOT_NAMES[slot.key] ?? T.TABLE_FIGURES[slot.key]?.name ?? (slot.key.startsWith('codes-') ? `${T.sectionCodes(text, slot.key.slice(6), where).heading} by code` : null);
  if (slot.key.startsWith('pattern-')) {
    const p = T.patternStrips(text, where)[Number(slot.key.slice(8))];
    if (!p) throw new Error(`${where}: §12.5 has no pattern fence for ${slot.key}`);
    return `Pattern: ${p.name}, from §${slot.section.trim()}`;
  }
  if (name === null) throw new Error(`spec twin: no title for the figure slot ${slot.key}`);
  return `${name}, from §${slot.section.trim()}`;
}

/** Names of the slots whose title does not come from the text (as in SpecFigure.astro). */
const SLOT_NAMES: Record<string, string> = {
  requirements: 'Where the requirements are',
  'safety-order': 'Safety ordering',
  layers: 'Layer model',
  edges: 'Edge types',
  safety: 'Safety-critical capabilities',
  step: 'Step anatomy',
  'safety-defaults': 'Safety defaults by capability',
  reference: 'Anatomy of a reference',
  annotations: 'Annotation types',
  gates: 'Gate outcomes',
  failures: 'Failure actions',
  precedence: 'Operator precedence',
  'static-checks': 'Static checks and their codes',
  extensions: 'Extensions and what they unlock',
  triggers: 'How runs start',
  'recovery-loop': 'Recovery loop',
  'recovery-replay': 'A recovery that runs out',
  'wait-timeline': 'A wait on a timeline',
  'silent-source': 'Recovering a silent source',
  'wait-replay': 'A wait that loses its source',
  approval: 'Who decides, and what then',
  'deferral-replay': 'What a deferral reaches',
  delegate: 'What a delegate binds',
  quorum: 'A quorum tally',
  'quorum-fields': 'Quorum fields and the codes they raise',
  'trust-classes': 'Trust classes',
  'sender-filter': 'The sender filter',
  'schema-shelf': 'Schema shelf',
  'merge-thresholds': 'Merge thresholds',
  decay: 'Decay with a floor: reference configuration',
  families: 'Diagnostic families',
  'code-heat': 'Where codes are raised',
  levels: 'What each level checks',
  suite: 'The conformance suite',
  bumps: 'Which change bumps which number',
  'checkpoint-tree': 'Checkpoint decision tree',
  categories: 'Error categories',
};

/** The decision tree as a nested list: each question, its answers and where they lead. */
function treeList(n: T.TreeNode, depth = 0): string[] {
  const pad = '  '.repeat(depth);
  return n.branches.flatMap((b) => [`${pad}- ${b.answer}: ${b.node.text}`, ...treeList(b.node, depth + 1)]);
}

/**
 * The block of one figure slot that has no data-table block of its own: its
 * title and caption, and what the figure works out from its source.
 */
export function slotBlock(slot: SpecSlot, source: string): string {
  const text = readRepoFile(source);
  const where = source;
  const title = slotTitle(slot, text, where);
  const at = `§${slot.section.trim()}`;
  const drawn = (what: string) => `The figure draws the ${what} of ${at} above.`;
  switch (slot.key) {
    case 'reference':
      return figure(title, referenceCaption(bindingExamples(text, where)), drawn('examples'));
    case 'annotations': {
      const g = annotationGrammar(text, where);
      return figure(title, annotationCaption(g.names, annotationGroups(g.names)), `Type names: ${g.names.map(code).join(', ')}.`);
    }
    case 'failures': {
      const f = failureBranches(text, where, loadCatalogSchema());
      return figure(title, failureCaption(f), `Actions: ${f.map((b) => code(b.action)).join(', ')}.`);
    }
    case 'precedence': {
      const rungs = D.precedenceLadder(text, where);
      return figure(
        title,
        D.precedenceCaption(rungs),
        table(
          ['Level, loosest first', 'Rule', 'Operators', 'Note'],
          rungs.map((r, i) => [i === rungs.length - 1 ? 'operands' : String(i + 1), code(r.rule), r.operators.map(code).join(', '), r.note ? cell(r.note) : '']),
        ),
      );
    }
    case 'static-checks':
      return figure(title, D.staticChecksCaption(text, where), drawn('table'));
    case 'triggers':
      return figure(title, D.triggersCaption(D.triggerTiles(text, where).tiles), drawn('table'));
    case 'recovery-loop':
      return figure(title, D.recoveryCaption(D.recoveryRows(text, where)), drawn('tables'));
    case 'wait-timeline':
      return figure(title, D.waitCaption(D.waitTimeline(text, where)), drawn('example step'));
    case 'silent-source':
      return figure(title, D.silentCaption(D.silentSource(text, where)), drawn('example failure modes'));
    case 'quorum': {
      const q = D.quorumExample(text, where);
      return figure(
        title,
        D.quorumCaption(q),
        table(
          ['Vote', 'Counts as'],
          [...q.pass.map((v) => [code(v), 'a pass']), ...q.blocking.map((v) => [code(v), 'blocking']), ...q.other.map((v) => [code(v), 'neither side'])],
        ) + `\n\nReviewers: ${q.reviewers.map(code).join(', ')}; passes needed: ${q.minPass}${q.minFull ? `, ${q.minFull} of them full-scope` : ''}.`,
      );
    }
    case 'quorum-fields':
      return figure(title, D.quorumFieldsCaption(D.quorumFieldCodes(text, where)), drawn('table'));
    case 'sender-filter': {
      const rows = D.senderFilter(text, where);
      return figure(title, D.senderCaption(rows), table(['Input', 'Drops an item'], rows.map((r) => [code(r.input), r.drops ? 'Yes' : 'No'])));
    }
    case 'schema-shelf':
      return figure(title, T.shelfCaption(T.schemaShelf(text, where)), drawn('table'));
    case 'levels': {
      const cols = T.conformanceLevels(text, where);
      return figure(title, T.levelsCaption(cols), table(['Level', 'Name', 'Requirements listed'], cols.map((c) => [c.level, c.name, String(c.items.length)])));
    }
    case 'bumps': {
      const b = T.versionBumps(text, where);
      return figure(title, T.bumpsCaption(b), table(['Version number', 'Changes that bump it'], b.map((x) => [x.bump, x.changes.map(cell).join('; ')])));
    }
    case 'checkpoint-tree': {
      const t = T.decisionTree(text, where);
      return figure(title, T.treeCaption(t), [`${t.text}`, '', ...treeList(t)].join('\n'));
    }
    case 'categories': {
      const c = T.categoryCounts(text, where);
      return figure(title, T.categoryCaption(c), table(['Category', 'Range', 'Codes'], c.map((x) => [x.name, code(x.range), String(x.count)])));
    }
  }
  if (slot.key.startsWith('codes-')) return figure(title, T.sectionCodesCaption(T.sectionCodes(text, slot.key.slice(6), where)), drawn('table'));
  if (slot.key in T.TABLE_FIGURES) return figure(title, T.tableFigureCaption(slot.key, text, where), `The figure is the table of ${at} above.`);
  if (slot.key.startsWith('pattern-')) {
    const p = T.patternStrips(text, where)[Number(slot.key.slice(8))]!;
    return figure(
      title,
      T.patternCaption(p),
      p.wf.steps.map((s) => `${s.index}. ${code(s.capability)}${s.store_as ? ` as ${code(s.store_as)}` : ''}${s.consumes.length > 0 ? `, reads ${s.consumes.map(code).join(', ')}` : ''}`).join('\n'),
    );
  }
  throw new Error(`spec twin: the figure slot ${slot.key} has no Markdown block`);
}

/**
 * The "Figures on this page" section of a Standard's Markdown copy: one block
 * per slot, in page order. `rich` holds the blocks with a data table of their
 * own, keyed by figure title; every one must match a slot.
 */
export function slotBlocks(slots: readonly SpecSlot[], source: string, rich: readonly string[]): string[] {
  const text = readRepoFile(source);
  const byTitle = new Map(rich.map((b) => [/^\*\*Figure: (.*?)\.\*\* /.exec(b)?.[1] ?? '', b]));
  const used = new Set<string>();
  const out = slots.map((s) => {
    const t = slotTitle(s, text, source);
    const b = byTitle.get(t);
    if (b !== undefined) {
      used.add(t);
      return b;
    }
    return slotBlock(s, source);
  });
  const stray = [...byTitle.keys()].filter((t) => !used.has(t));
  if (stray.length > 0) throw new Error(`spec twin: ${source}: blocks with no figure on the page: ${stray.join('; ')}`);
  return ['## Figures on this page', ...out];
}
