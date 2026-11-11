// Domain profiles from schemas/profiles/*.yaml (not profile_schema.yaml),
// joined to docs/domains/<domain>/README.md. The domain key is the profile's
// `domain` field, which must equal the file name with `_` changed to `-`.
import { parse } from 'yaml';
import { readRepoFile, trackedUnder, TRACKED_FILES } from '../lib/repo';
import { loadWorkflows } from './workflows';

export const PROFILE_DIR = 'schemas/profiles';
export const PROFILE_SCHEMA = 'schemas/profiles/profile_schema.yaml';

export interface DomainProfile {
  /** The profile's `domain` field, e.g. `data-analysis`. Also the URL slug. */
  key: string;
  profileFile: string;
  readme: string | null;
  version: string;
  description: string;
  profile: Record<string, unknown>;
  /** Workflow ids the profile lists; `defined` is false when no catalog defines it. */
  workflows: { id: string; defined: boolean }[];
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

export function buildProfile(file: string, doc: unknown, definedIds: ReadonlySet<string>): DomainProfile {
  if (!isObj(doc)) throw new Error(`profiles: ${file} is not a mapping`);
  const key = doc.domain;
  if (typeof key !== 'string') throw new Error(`profiles: ${file} has no domain field`);
  const stem = file.replace(/^.*\//, '').replace(/\.yaml$/, '');
  if (key !== stem.replace(/_/g, '-')) {
    throw new Error(`profiles: ${file} declares domain ${key}, expected ${stem.replace(/_/g, '-')}`);
  }
  if (typeof doc.version !== 'string') throw new Error(`profiles: ${file} version must be a string`);
  const list = doc.workflows ?? [];
  if (!Array.isArray(list) || !list.every((w) => typeof w === 'string')) {
    throw new Error(`profiles: ${file} workflows must be a list of ids`);
  }
  const readmePath = `docs/domains/${key}/README.md`;
  return {
    key,
    profileFile: file,
    readme: TRACKED_FILES.has(readmePath) ? readmePath : null,
    version: doc.version,
    description: typeof doc.description === 'string' ? doc.description.trim() : '',
    profile: doc,
    workflows: (list as string[]).map((id) => ({ id, defined: definedIds.has(id) })),
  };
}

let cached: DomainProfile[] | undefined;

/** Profiles in key order. Also checks each workflow's `domain` and `profile` agree. */
export function loadProfiles(): DomainProfile[] {
  if (cached) return cached;
  const wfs = loadWorkflows();
  const defined = new Set(wfs.all.map((w) => w.id));
  const files = trackedUnder(PROFILE_DIR, '.yaml').filter((f) => f !== PROFILE_SCHEMA);
  const profiles = files
    .map((f) => buildProfile(f, parse(readRepoFile(f)), defined))
    .sort((a, b) => a.key.localeCompare(b.key));
  const byFile = new Map(profiles.map((p) => [p.profileFile, p]));
  for (const wf of wfs.all) {
    if (wf.profile === undefined && wf.domain === undefined) continue;
    const p = wf.profile === undefined ? undefined : byFile.get(wf.profile);
    if (!p) throw new Error(`workflows: ${wf.id} names profile ${String(wf.profile)}, which is not a profile file`);
    if (p.key !== wf.domain) {
      throw new Error(`workflows: ${wf.id} has domain ${String(wf.domain)} but its profile is for ${p.key}`);
    }
  }
  cached = profiles;
  return cached;
}
