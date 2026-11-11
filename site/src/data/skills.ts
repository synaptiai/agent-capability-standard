// skills/<dir>/SKILL.md joined to the ontology and the workflow catalogs.
// A directory named after a capability renders inside that capability's page.
// Any other directory must be in COMPOSED_SKILLS, or loading fails.
import { parse } from 'yaml';
import { readRepoFile, TRACKED_FILES } from '../lib/repo';
import { loadOntology } from './ontology';
import { loadWorkflows } from './workflows';

/** Composed skills and the workflow each one runs (null: runs no catalog workflow). */
export const COMPOSED_SKILLS: Readonly<Record<string, string | null>> = {
  'capability-gap-analysis': 'capability_gap_analysis',
  'debug-workflow': 'debug_code_change',
  'digital-twin-bootstrap': 'digital_twin_bootstrap',
  'digital-twin-sync-loop': 'digital_twin_sync_loop',
  'discover-capabilities': null,
  'perspective-validation': null,
};

export interface SkillRef {
  /** Directory name under skills/. */
  dir: string;
  /** Frontmatter `name`: the name the skill is invoked by. */
  name: string;
  description: string;
  source: string;
  kind: 'capability' | 'composed';
  capability?: string;
  workflow?: string;
  frontmatter: Record<string, unknown>;
}

export function parseFrontmatter(text: string, where: string): Record<string, unknown> {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/.exec(text);
  if (!m) throw new Error(`skills: ${where} has no frontmatter`);
  const fm: unknown = parse(m[1]!);
  if (typeof fm !== 'object' || fm === null || Array.isArray(fm)) {
    throw new Error(`skills: ${where} frontmatter is not a mapping`);
  }
  return fm as Record<string, unknown>;
}

let cached: SkillRef[] | undefined;

export function loadSkills(): SkillRef[] {
  if (cached) return cached;
  const ontology = loadOntology();
  const workflows = loadWorkflows();
  const sources = [...TRACKED_FILES].filter((p) => /^skills\/[^/]+\/SKILL\.md$/.test(p)).sort();
  const skills = sources.map((source): SkillRef => {
    const dir = source.split('/')[1]!;
    const fm = parseFrontmatter(readRepoFile(source), source);
    if (typeof fm.name !== 'string' || typeof fm.description !== 'string') {
      throw new Error(`skills: ${source} needs a string name and description`);
    }
    const base = { dir, name: fm.name, description: fm.description, source, frontmatter: fm };
    if (ontology.byId.has(dir)) return { ...base, kind: 'capability', capability: dir };
    if (!(dir in COMPOSED_SKILLS)) {
      throw new Error(`skills: ${dir} is neither a capability id nor listed in COMPOSED_SKILLS`);
    }
    const wf = COMPOSED_SKILLS[dir];
    if (wf === null || wf === undefined) return { ...base, kind: 'composed' };
    if (!workflows.byId.has(wf)) throw new Error(`skills: ${dir} joins to unknown workflow ${wf}`);
    return { ...base, kind: 'composed', workflow: wf };
  });
  for (const c of ontology.capabilities) {
    if (!skills.some((s) => s.capability === c.id)) {
      throw new Error(`skills: capability ${c.id} has no skills/${c.id}/SKILL.md`);
    }
  }
  for (const dir of Object.keys(COMPOSED_SKILLS)) {
    if (!skills.some((s) => s.dir === dir)) throw new Error(`skills: COMPOSED_SKILLS names missing ${dir}`);
  }
  cached = skills;
  return cached;
}
