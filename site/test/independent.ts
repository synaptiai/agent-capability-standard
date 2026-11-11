// Expected values for tests on live repository data, read at test time from
// sources the loaders under test do not use, or by a simpler method than
// theirs (plain text scans instead of a YAML parse). A routine change, such as
// adding a capability or workflow or bumping a release version, then moves the
// expected value and the loader's output together, while a loader bug still
// shows up as a disagreement.
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

const REPO = path.resolve(process.cwd(), '..');

export function repoText(repoPath: string): string {
  return readFileSync(path.join(REPO, repoPath), 'utf8');
}

/** Lines of the first Markdown section whose heading line matches, up to the next heading of any level. */
export function sectionLines(text: string, heading: RegExp): string[] {
  const lines = text.split('\n');
  const start = lines.findIndex((l) => heading.test(l));
  if (start === -1) throw new Error(`independent: no heading matches ${heading}`);
  const rest = lines.slice(start + 1);
  const end = rest.findIndex((l) => /^#{1,6} /.test(l));
  return end === -1 ? rest : rest.slice(0, end);
}

export interface LayerRow {
  id: string;
  count: number;
  capabilities: string[];
}

/**
 * The "Layer Architecture" table of CLAUDE.md. The "Creating New
 * Capabilities" checklist there keeps it current.
 */
export function claudeLayerTable(): LayerRow[] {
  const rows = sectionLines(repoText('CLAUDE.md'), /^### Layer Architecture$/)
    .filter((l) => /^\| [A-Z]+ \|/.test(l))
    .map((l) => l.split('|').map((c) => c.trim()))
    .map(([, id, , count, caps]) => ({
      id: id!,
      count: Number(count),
      capabilities: caps!.split(',').map((c) => c.trim()),
    }));
  if (rows.length === 0) throw new Error('independent: CLAUDE.md has no layer rows');
  for (const r of rows) {
    if (r.count !== r.capabilities.length) throw new Error(`independent: CLAUDE.md row ${r.id} disagrees with itself`);
  }
  return rows;
}

/** Top-level mapping keys of a YAML file, by a line scan; `x-` vendor keys are left out. */
export function topLevelKeys(text: string): string[] {
  return [...text.matchAll(/^([A-Za-z_][A-Za-z0-9_]*):/gm)].map((m) => m[1]!);
}

/** Workflow files: the core catalog and every domain catalog, by directory listing. */
export function catalogFiles(): { core: string; domain: string[] } {
  const domain = readdirSync(path.join(REPO, 'schemas/workflows'))
    .filter((f) => f.endsWith('.yaml'))
    .sort()
    .map((f) => `schemas/workflows/${f}`);
  return { core: 'schemas/workflow_catalog.yaml', domain };
}

/** Steps of a catalog: lines that open a list item with `capability:`. */
export function stepLineCount(text: string): number {
  return (text.match(/^\s*- capability:/gm) ?? []).length;
}

/** Domain profile files, by directory listing; the schema file is not a profile. */
export function profileFiles(): string[] {
  return readdirSync(path.join(REPO, 'schemas/profiles'))
    .filter((f) => f.endsWith('.yaml') && f !== 'profile_schema.yaml')
    .sort();
}

/** The workflow ids a profile lists under its top-level `workflows:` key. */
export function profileWorkflowIds(text: string): string[] {
  const lines = text.split('\n');
  const start = lines.findIndex((l) => l === 'workflows:');
  if (start === -1) return [];
  const ids: string[] = [];
  for (const l of lines.slice(start + 1)) {
    const m = /^ {2}- ([a-z0-9_]+)\s*$/.exec(l);
    if (!m) break;
    ids.push(m[1]!);
  }
  return ids;
}

/** skills/README.md: its "Total" line and the names in the Composed Skills table. */
export function skillsReadme(): { atomic: number; composed: number; total: number; composedNames: string[] } {
  const text = repoText('skills/README.md');
  const m = /\*\*Total: (\d+) atomic capabilities \+ (\d+) composed skills = (\d+) skills\*\*/.exec(text);
  if (!m) throw new Error('independent: skills/README.md has no Total line');
  const composedNames = sectionLines(text, /^## Composed Skills/).flatMap((l) => {
    const c = /^\| `([^`]+)` \|/.exec(l);
    return c ? [c[1]!] : [];
  });
  return { atomic: Number(m[1]), composed: Number(m[2]), total: Number(m[3]), composedNames };
}

/** Versions of the Standard, from the file names in spec/, newest first. */
export function standardFileVersions(): string[] {
  const num = (v: string) => v.split('.').map(Number);
  return readdirSync(path.join(REPO, 'spec'))
    .flatMap((f) => {
      const m = /^STANDARD-v(\d+\.\d+\.\d+)\.md$/.exec(f);
      return m ? [m[1]!] : [];
    })
    .sort((a, b) => {
      const [x, y] = [num(a), num(b)];
      for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return y[i]! - x[i]!;
      return 0;
    });
}

/** Rows of the §9.2 to §9.7 diagnostic tables of a Standard, counted per subsection by a line scan. */
export function diagnosticRowsPerSection(text: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const n of ['9.2', '9.3', '9.4', '9.5', '9.6', '9.7']) {
    const heading = new RegExp(`^### ${n.replace('.', '\\.')} `);
    out[n] = sectionLines(text, heading).filter((l) => /^\| [A-Z]\d{3} \|/.test(l)).length;
  }
  return out;
}
