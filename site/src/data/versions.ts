// Every version the site shows, read from the files that own it.
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
  cached = {
    standard: { current, previous },
    ontology: loadOntology().version,
    plugin: plugin.version,
    pythonPackage: pyprojectVersion(readRepoFile('pyproject.toml')),
    commit: COMMIT_SHA,
    buildDate: new Date().toISOString().slice(0, 10),
  };
  return cached;
}
