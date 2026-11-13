// Figures of the domains index (visual spec 3.6) placed in the README's own
// sections: under each "Choosing a Domain" H3, what that profile sets; and
// under "How Domains Demonstrate Domain-Agnostic Capabilities", the domain
// parameter the capability that section names takes in each catalog's
// workflows. The page and its Markdown copy both call these functions.
import type { Heading, RootContent } from 'mdast';
import { loadOntology } from '../data/ontology';
import type { DomainProfile } from '../data/profiles';
import { loadWorkflows } from '../data/workflows';
import { headingText, parseMarkdown } from './anchors';
import { approvalLadder, checkpointPolicy, ladderCaption, policyWord, type Ladder } from './domain-figures';
import { andList, plural } from './words';

const squash = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');

/** The README section the per-profile figures go into (its GitHub id). */
export const CHOOSING_ANCHOR = 'choosing-a-domain';
/** The README section the domain-parameter figure goes under (its GitHub id). */
export const AGNOSTIC_ANCHOR = 'how-domains-demonstrate-domain-agnostic-capabilities';

/** The profile key an H3 title names ("Multi-modal" -> multimodal), or null. */
export function headingProfileKey(title: string, keys: readonly string[]): string | null {
  return keys.find((k) => squash(k) === squash(title)) ?? null;
}

export interface Glance {
  key: string;
  ladder: Ladder | null;
  triggers: number;
  /** "4 always, 1 high risk", or null with no triggers. */
  triggerLevels: string | null;
  defined: number;
  proposed: number;
}

export function glance(d: DomainProfile): Glance {
  const policy = checkpointPolicy(d.profile);
  return {
    key: d.key,
    ladder: approvalLadder(d.profile),
    triggers: policy?.triggers.length ?? 0,
    triggerLevels: policy && policy.triggers.length > 0 ? andList(policy.levels.map((l) => `${l.count} ${policyWord(l.level)}`)) : null,
    defined: d.workflows.filter((w) => w.defined).length,
    proposed: d.workflows.filter((w) => !w.defined).length,
  };
}

export function glanceTitle(g: Glance): string {
  return `What the ${g.key} profile sets`;
}

export function glanceCaption(g: Glance): string {
  const ladder = g.ladder ? ladderCaption(g.ladder) : 'The profile sets no risk thresholds.';
  return `${ladder} It names ${plural(g.triggers, 'checkpoint trigger')} and ${plural(g.defined + g.proposed, 'workflow')}.`;
}

export interface ParameterRow {
  /** A domain key, or null for the reference catalog. */
  domain: string | null;
  values: { value: string; workflows: string[] }[];
}

export interface ParameterAcross {
  capability: string;
  title: string;
  caption: string;
  rows: ParameterRow[];
}

/** The first backticked ontology id in a section's paragraphs, in source order. */
function namedCapability(blocks: RootContent[]): string | null {
  const known = new Set(loadOntology().capabilities.map((c) => c.id));
  for (const b of blocks) {
    if (b.type !== 'paragraph') continue;
    for (const c of b.children) if (c.type === 'inlineCode' && known.has(c.value)) return c.value;
  }
  return null;
}

/**
 * The domain parameter values the capability named in the README's
 * "How Domains Demonstrate ..." section takes in each catalog's steps,
 * reference catalog first, then the domain catalogs. Null when the README
 * has no such section or it names no capability.
 */
export function parameterAcross(readmeText: string): ParameterAcross | null {
  const nodes = parseMarkdown(readmeText).children;
  const i = nodes.findIndex((n) => n.type === 'heading' && n.depth === 2 && headingText(n).startsWith('How Domains Demonstrate'));
  if (i === -1) return null;
  const end = nodes.findIndex((n, j) => j > i && n.type === 'heading' && (n as Heading).depth <= 2);
  const cap = namedCapability(nodes.slice(i + 1, end === -1 ? undefined : end));
  if (!cap) return null;
  const { core, domain } = loadWorkflows();
  const catalogs: { domain: string | null; wfs: typeof core }[] = [
    { domain: null, wfs: core },
    ...[...new Set(domain.map((w) => w.domain!))].map((k) => ({ domain: k, wfs: domain.filter((w) => w.domain === k) })),
  ];
  const rows = catalogs
    .map((c) => {
      const m = new Map<string, string[]>();
      for (const w of c.wfs) {
        for (const s of w.steps) {
          if (s.capability !== cap || !s.domain) continue;
          const list = m.get(s.domain) ?? [];
          if (!list.includes(w.id)) list.push(w.id);
          m.set(s.domain, list);
        }
      }
      return { domain: c.domain, values: [...m].map(([value, workflows]) => ({ value, workflows })) };
    })
    .filter((r) => r.values.length > 0);
  const all = new Set(rows.flatMap((r) => r.values.map((v) => v.value)));
  const shared = [...all].filter((v) => rows.filter((r) => r.values.some((x) => x.value === v)).length > 1);
  const caption =
    `Across ${plural(rows.length, 'catalog')}, ${cap} steps take ${plural(all.size, 'domain value')}` +
    (shared.length === 0 ? ', and no value appears in more than one catalog.' : `; only ${andList(shared)} ${shared.length === 1 ? 'appears' : 'appear'} in more than one catalog.`);
  return { capability: cap, title: `The domain parameter of ${cap} in each catalog's workflows`, caption, rows };
}
