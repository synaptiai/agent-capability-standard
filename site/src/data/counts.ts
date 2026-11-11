// Every count the site shows, computed from the data. Site copy uses these
// values; no count is typed into a template.
import { loadDiagnostics } from './diagnostics';
import { loadOntology } from './ontology';
import { loadProfiles } from './profiles';
import { loadSkills } from './skills';
import { loadWorkflows } from './workflows';

export interface Counts {
  capabilityCount: number;
  layerCount: number;
  edgeCount: number;
  edgeTypeCount: number;
  workflowCount: number;
  coreWorkflowCount: number;
  domainWorkflowCount: number;
  stepCount: number;
  profileCount: number;
  undefinedProfileWorkflowCount: number;
  diagnosticCount: number;
  skillCount: number;
  composedSkillCount: number;
  /** Capabilities per layer id, in ontology order. */
  capabilitiesPerLayer: Record<string, number>;
}

let cached: Counts | undefined;

export function loadCounts(): Counts {
  if (cached) return cached;
  const o = loadOntology();
  const w = loadWorkflows();
  const p = loadProfiles();
  const s = loadSkills();
  cached = {
    capabilityCount: o.capabilities.length,
    layerCount: o.layers.length,
    edgeCount: o.edges.length,
    edgeTypeCount: o.edgeTypes.length,
    workflowCount: w.all.length,
    coreWorkflowCount: w.core.length,
    domainWorkflowCount: w.domain.length,
    stepCount: w.all.reduce((n, wf) => n + wf.steps.length, 0),
    profileCount: p.length,
    undefinedProfileWorkflowCount: p.reduce((n, d) => n + d.workflows.filter((x) => !x.defined).length, 0),
    diagnosticCount: loadDiagnostics().length,
    skillCount: s.length,
    composedSkillCount: s.filter((x) => x.kind === 'composed').length,
    capabilitiesPerLayer: Object.fromEntries(o.layers.map((l) => [l.id, l.capabilities.length])),
  };
  return cached;
}
