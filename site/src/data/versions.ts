// Every version the site shows, read from the files that own it.
import { computeAnchors } from '../lib/anchors';
import { COMMIT_SHA, readRepoFile, TRACKED_FILES } from '../lib/repo';
import { loadOntology } from './ontology';

export interface StandardVersion {
  version: string;
  /** The first clause of the `**Status:**` line, e.g. "Candidate Standard". */
  status: string;
  date: string | null;
  source: string;
}

export interface Versions {
  standard: { current: StandardVersion; previous: StandardVersion[] };
  ontology: string;
  plugin: string;
  pythonPackage: string;
  /** `@synaptiai/acs-core`, from `packages/acs-core/package.json`. */
  typescriptPackage: string;
  commit: string;
  buildDate: string;
}

function cmpSemver(a: string, b: string): number {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) if (pa[i] !== pb[i]) return (pa[i] ?? 0) - (pb[i] ?? 0);
  return 0;
}

export function parseStandardHeader(source: string, text: string): StandardVersion {
  const fromName = /STANDARD-v(\d+\.\d+\.\d+)\.md$/.exec(source)?.[1];
  const version = /^\*\*Version:\*\*\s*(\S+)/m.exec(text)?.[1];
  const statusLine = /^\*\*Status:\*\*\s*(.+)$/m.exec(text)?.[1];
  if (!version || !statusLine) throw new Error(`versions: ${source} lacks a Version or Status line`);
  if (version !== fromName) throw new Error(`versions: ${source} says Version ${version}`);
  const status = statusLine.split(/\s+[—–-]\s+|;/)[0]!.trim();
  const date = /^\*\*Date:\*\*\s*(\S+)/m.exec(text)?.[1] ?? null;
  return { version, status, date, source };
}

export function standardVersions(): StandardVersion[] {
  return [...TRACKED_FILES]
    .filter((p) => /^spec\/STANDARD-v\d+\.\d+\.\d+\.md$/.test(p))
    .map((p) => parseStandardHeader(p, readRepoFile(p)))
    .sort((a, b) => cmpSemver(b.version, a.version));
}

/**
 * A version's status as a sentence complement, from its header status (the
 * statuses are defined under "Standard versions" in spec/GOVERNANCE.md):
 * "the released Standard", "a Candidate Standard", "Supported", "Unsupported".
 */
export function statusPhrase(status: string): string {
  if (status === 'Standard') return 'the released Standard';
  if (status === 'Candidate Standard') return 'a Candidate Standard';
  return status;
}

export interface OlderVersionNote {
  /** The newest Standard's "Appendix X: Changes from <version>" heading, if it has one. */
  changes: { label: string; anchor: string } | null;
}

/**
 * Where the newest Standard lists the changes from an older version: its H2
 * "Appendix X: Changes from <version>", or null when it has none. The older
 * version's status comes from its own header, not from this text.
 */
export function olderVersionNote(version: string, currentText: string): OlderVersionNote {
  const heading = computeAnchors(currentText).entries.find(
    (h) => h.depth === 2 && new RegExp(`^(Appendix [A-Z]+): Changes from ${version.replace(/[\\^$.*+?()[\]{}|]/g, '\\$&')}$`).test(h.text),
  );
  const changes = heading ? { label: heading.text.split(':')[0]!, anchor: heading.slug } : null;
  return { changes };
}

function pyprojectVersion(text: string): string {
  const project = /^\[project\]\s*$([\s\S]*?)(?=^\[|(?![\s\S]))/m.exec(text)?.[1] ?? '';
  const v = /^version\s*=\s*"([^"]+)"/m.exec(project)?.[1];
  if (!v) throw new Error('versions: pyproject.toml [project] has no version');
  return v;
}

let cached: Versions | undefined;

export function loadVersions(): Versions {
  if (cached) return cached;
  const [current, ...previous] = standardVersions();
  if (!current) throw new Error('versions: no spec/STANDARD-v*.md file is tracked');
  const plugin = JSON.parse(readRepoFile('.claude-plugin/plugin.json')) as { version?: unknown };
  if (typeof plugin.version !== 'string') throw new Error('versions: plugin.json has no version');
  const tsPackage = JSON.parse(readRepoFile('packages/acs-core/package.json')) as { version?: unknown };
  if (typeof tsPackage.version !== 'string') throw new Error('versions: packages/acs-core/package.json has no version');
  cached = {
    standard: { current, previous },
    ontology: loadOntology().version,
    plugin: plugin.version,
    pythonPackage: pyprojectVersion(readRepoFile('pyproject.toml')),
    typescriptPackage: tsPackage.version,
    commit: COMMIT_SHA,
    buildDate: new Date().toISOString().slice(0, 10),
  };
  return cached;
}
