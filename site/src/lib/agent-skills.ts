// The agent skills discovery index (Agent Skills Discovery RFC v0.2.0,
// github.com/cloudflare/agent-skills-discovery-rfc): one entry per
// skills/*/SKILL.md, with the name and description of its front matter, type
// "skill-md", the URL of the copy served at
// /.well-known/agent-skills/<name>/SKILL.md, and the SHA-256 digest of
// exactly the bytes served there (the file as committed, unchanged).
//
// The RFC limits a name to 1-64 lowercase letters, digits and single
// hyphens, not at either end, and a description to 1024 characters; a skill
// that breaks either fails the build. A skill's name is its front matter
// name, which for two skills differs from its directory; the served copy
// lives under the name.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { parse } from 'yaml';
import { AGENT_SKILLS_DIR } from './agent-contract';
import { REPO_ROOT, TRACKED_FILES } from './repo';

export const SKILLS_SCHEMA = 'https://schemas.agentskills.io/discovery/0.2.0/schema.json';
const NAME = /^(?!-)(?!.*--)[a-z0-9-]{1,64}(?<!-)$/;

export interface SkillEntry {
  name: string;
  type: 'skill-md';
  description: string;
  url: string;
  digest: string;
}

export interface Skill {
  entry: SkillEntry;
  source: string;
  bytes: Buffer;
}

/** The front matter of a SKILL.md as an object. */
export function skillFrontmatter(text: string, source: string): { name: string; description: string } {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/.exec(text);
  if (!m) throw new Error(`agent-skills: ${source} has no front matter`);
  let fm: unknown;
  try {
    fm = parse(m[1]!);
  } catch (e) {
    throw new Error(`agent-skills: ${source} front matter is not valid YAML: ${(e as Error).message}`);
  }
  if (fm === null || typeof fm !== 'object') throw new Error(`agent-skills: ${source} front matter is empty or not a mapping`);
  const rec = fm as Record<string, unknown>;
  if (typeof rec.name !== 'string' || typeof rec.description !== 'string') throw new Error(`agent-skills: ${source} lacks a name or description`);
  const { name, description } = fm as { name: string; description: string };
  return { name, description: description.trim() };
}

export function sha256(bytes: Buffer): string {
  return `sha256:${createHash('sha256').update(bytes).digest('hex')}`;
}

let cached: Skill[] | undefined;

/** Every skill, sorted by name. */
export function loadSkills(): Skill[] {
  if (cached) return cached;
  const sources = [...TRACKED_FILES].filter((p) => /^skills\/[^/]+\/SKILL\.md$/.test(p)).sort();
  const skills = sources.map((source) => {
    const bytes = readFileSync(path.join(REPO_ROOT, source));
    const { name, description } = skillFrontmatter(bytes.toString('utf8'), source);
    if (!NAME.test(name)) throw new Error(`agent-skills: ${source} has the name "${name}", which the discovery RFC does not allow`);
    if (description.length === 0 || description.length > 1024) throw new Error(`agent-skills: the description of ${source} is ${description.length} characters (1 to 1024 allowed)`);
    const entry: SkillEntry = { name, type: 'skill-md', description, url: `${AGENT_SKILLS_DIR}${name}/SKILL.md`, digest: sha256(bytes) };
    return { entry, source, bytes };
  });
  const seen = new Map<string, string>();
  for (const s of skills) {
    const other = seen.get(s.entry.name);
    if (other) throw new Error(`agent-skills: ${other} and ${s.source} both have the name ${s.entry.name}`);
    seen.set(s.entry.name, s.source);
  }
  cached = skills.sort((a, b) => a.entry.name.localeCompare(b.entry.name));
  return cached;
}

export function skillsIndex(): { $schema: string; skills: SkillEntry[] } {
  return { $schema: SKILLS_SCHEMA, skills: loadSkills().map((s) => s.entry) };
}
