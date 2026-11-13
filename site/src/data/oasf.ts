// schemas/interop/oasf_mapping.yaml as typed data: one row per top-level OASF
// category, then one per GA extension (a GA-native capability with no OASF
// equivalent), each with its mapping type and the capabilities it maps to.
// Every capability id must be in the ontology and every mapping type one of
// the file's five, or loading fails.
import { parse } from 'yaml';
import { readRepoFile } from '../lib/repo';
import { loadOntology } from './ontology';

export const OASF_MAPPING_SOURCE = 'schemas/interop/oasf_mapping.yaml';

/** The mapping types the file's header lists, in that order. */
export const OASF_MAPPING_TYPES = ['direct', 'domain', 'composition', 'workflow', 'ga_extension'] as const;
export type OasfMappingType = (typeof OASF_MAPPING_TYPES)[number];

export interface OasfRow {
  /** The OASF category number ("1".."15") or the GA extension code ("GA-001"). */
  code: string;
  name: string;
  mappingType: OasfMappingType;
  capabilities: string[];
  /** A workflow the mapping names, when it names one. */
  workflow: string | null;
}

export interface OasfMapping {
  oasfVersion: string;
  /** Rows that are OASF categories; the rest are GA extensions. */
  categories: number;
  rows: OasfRow[];
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

export function buildOasfMapping(doc: unknown, known: ReadonlySet<string>): OasfMapping {
  if (!isObj(doc) || !isObj(doc.meta) || !isObj(doc.categories)) throw new Error(`oasf: ${OASF_MAPPING_SOURCE} needs meta and categories`);
  const problems: string[] = [];
  const row = (code: string, v: unknown): OasfRow | null => {
    if (!isObj(v) || typeof v.name !== 'string') {
      problems.push(`${code} has no name`);
      return null;
    }
    const type = v.mapping_type;
    if (!OASF_MAPPING_TYPES.includes(type as OasfMappingType)) problems.push(`${code} has mapping_type ${String(type)}`);
    const caps = Array.isArray(v.capabilities) ? v.capabilities.map(String) : [];
    if (caps.length === 0) problems.push(`${code} lists no capabilities`);
    for (const c of caps) if (!known.has(c)) problems.push(`${code} names ${c}, not in the ontology`);
    return { code, name: v.name, mappingType: type as OasfMappingType, capabilities: caps, workflow: typeof v.workflow === 'string' ? v.workflow : null };
  };
  const cats = Object.entries(doc.categories).map(([k, v]) => row(k, v));
  const ext = isObj(doc.ga_extensions) ? Object.entries(doc.ga_extensions).map(([k, v]) => row(k, v)) : [];
  if (problems.length > 0) throw new Error(`oasf: ${OASF_MAPPING_SOURCE}: ${problems.join('; ')}`);
  return {
    oasfVersion: String(doc.meta.oasf_version ?? ''),
    categories: cats.length,
    rows: [...cats, ...ext] as OasfRow[],
  };
}

let cached: OasfMapping | undefined;

export function loadOasfMapping(): OasfMapping {
  cached ??= buildOasfMapping(parse(readRepoFile(OASF_MAPPING_SOURCE)), new Set(loadOntology().byId.keys()));
  return cached;
}
