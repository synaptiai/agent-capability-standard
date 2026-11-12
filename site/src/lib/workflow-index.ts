// The workflow family map of the workflows index (visual spec 3.4, F-WI2), as
// data. The page and its Markdown copy both call these functions, so the
// figure and the copy's "**Figure:**" block say the same thing. Two figures,
// one above each table: the reference workflows, with the ones that run other
// workflows drawn as a family; and the domain workflows grouped by domain,
// with the workflows a domain profile lists that no catalog defines yet.
import { PROPOSED_WORKFLOWS } from '../data/proposed-workflows';
import { loadProfiles } from '../data/profiles';
import { loadWorkflows, type Workflow } from '../data/workflows';
import { stepList } from './workflow-figures';

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const andList = (xs: readonly string[]) => (xs.length <= 1 ? (xs[0] ?? '') : `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`);

export interface FamilyChild {
  workflow: Workflow;
  /** The parent's steps that run this workflow, ascending. */
  steps: number[];
}

export interface Family {
  parent: Workflow;
  children: FamilyChild[];
}

export interface ReferenceMap {
  title: string;
  caption: string;
  families: Family[];
  /** Reference workflows that neither run nor are run by another, in catalog order. */
  standalone: Workflow[];
}

/** The workflows a workflow runs (steps with `workflow_id`), in first-use order. */
export function runsWorkflows(wf: Workflow): FamilyChild[] {
  const { byId } = loadWorkflows();
  const out = new Map<string, number[]>();
  for (const s of wf.steps) {
    if (!s.workflow_id) continue;
    if (!byId.has(s.workflow_id)) throw new Error(`workflow-index: ${wf.id} step ${s.index} runs unknown workflow ${s.workflow_id}`);
    out.set(s.workflow_id, [...(out.get(s.workflow_id) ?? []), s.index]);
  }
  return [...out].map(([id, steps]) => ({ workflow: byId.get(id)!, steps }));
}

export function referenceMap(): ReferenceMap {
  const { core } = loadWorkflows();
  const families = core.map((wf) => ({ parent: wf, children: runsWorkflows(wf) })).filter((f) => f.children.length > 0);
  const inFamily = new Set(families.flatMap((f) => [f.parent.id, ...f.children.map((c) => c.workflow.id)]));
  const standalone = core.filter((w) => !inFamily.has(w.id));
  const runs = families.map(
    (f) => `${f.parent.id} runs ${andList(f.children.map((c) => `${c.workflow.id} (${stepList(c.steps)})`))}`,
  );
  const caption =
    families.length === 0
      ? `${plural(core.length, 'reference workflow', 'reference workflows')}, and none runs another.`
      : `${plural(core.length, 'reference workflow', 'reference workflows')}: ${runs.join('; ')}; the other ${standalone.length} run on their own.`;
  return { title: `${plural(core.length, 'reference workflow', 'reference workflows')}, and the workflows they run`, caption, families, standalone };
}

export interface DomainGroup {
  domain: string;
  /** Workflows a catalog defines for this domain, in catalog order. */
  defined: Workflow[];
  /** Ids the domain's profile lists that no catalog defines yet. */
  proposed: string[];
}

export interface DomainMap {
  title: string;
  caption: string;
  groups: DomainGroup[];
}

export function domainMap(): DomainMap {
  const { domain } = loadWorkflows();
  const profiles = loadProfiles();
  const keys = [...new Set([...domain.map((w) => w.domain!), ...profiles.map((p) => p.key)])];
  const groups = keys
    .map((k) => ({
      domain: k,
      defined: domain.filter((w) => w.domain === k),
      proposed: [...(PROPOSED_WORKFLOWS[k.replace(/-/g, '_')] ?? PROPOSED_WORKFLOWS[k] ?? [])],
    }))
    .filter((g) => g.defined.length + g.proposed.length > 0);
  const withCatalog = groups.filter((g) => g.defined.length > 0);
  const proposing = groups.filter((g) => g.proposed.length > 0);
  const proposedCount = proposing.reduce((n, g) => n + g.proposed.length, 0);
  const caption =
    `${plural(domain.length, 'domain workflow', 'domain workflows')} in ${plural(withCatalog.length, 'domain catalog', 'domain catalogs')}` +
    (proposedCount > 0
      ? `, and ${proposedCount} more that the ${andList(proposing.map((g) => g.domain))} ${proposing.length === 1 ? 'profile proposes' : 'profiles propose'} but no catalog defines yet.`
      : '.');
  return { title: 'Domain workflows by domain, with the proposed ones', caption, groups };
}

/** A workflow id with a break opportunity after each underscore, as HTML-safe pieces. */
export function idPieces(id: string): string[] {
  return id.split(/(?<=_)/);
}
