// CITATION.cff as typed data. spec/CITATION.cff must be byte-identical.
import { parse } from 'yaml';
import { GITHUB_BASE, readRepoFile } from '../lib/repo';

export const CITATION_SOURCE = 'CITATION.cff';
export const CITATION_COPY = 'spec/CITATION.cff';

export interface Citation {
  title: string;
  version: string;
  date_released: string;
  authors: { given: string; family: string }[];
  license: string;
  message: string;
  bibtex: string;
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

function str(o: Obj, k: string): string {
  const v = o[k];
  if (typeof v !== 'string') throw new Error(`citation: "${k}" must be a quoted string`);
  return v;
}

export function buildCitation(doc: unknown, repoUrl: string): Citation {
  if (!isObj(doc)) throw new Error('citation: CITATION.cff is not a mapping');
  const rawAuthors = doc.authors;
  if (!Array.isArray(rawAuthors) || rawAuthors.length === 0) throw new Error('citation: no authors');
  const authors = rawAuthors.map((a) => {
    if (!isObj(a)) throw new Error('citation: an author is not a mapping');
    return { given: str(a, 'given-names'), family: str(a, 'family-names') };
  });
  const title = str(doc, 'title');
  const version = str(doc, 'version');
  const date_released = str(doc, 'date-released');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date_released)) throw new Error('citation: date-released is not YYYY-MM-DD');
  const year = date_released.slice(0, 4);
  const bibtex = [
    `@misc{agentcapabilitystandard${year},`,
    `  title={${title}},`,
    `  author={${authors.map((a) => `${a.family}, ${a.given}`).join(' and ')}},`,
    `  year={${year}},`,
    `  version={${version}},`,
    `  url={${repoUrl}}`,
    '}',
  ].join('\n');
  return {
    title,
    version,
    date_released,
    authors,
    license: str(doc, 'license'),
    message: str(doc, 'message'),
    bibtex,
  };
}

let cached: Citation | undefined;

export function loadCitation(): Citation {
  if (cached) return cached;
  const text = readRepoFile(CITATION_SOURCE);
  if (readRepoFile(CITATION_COPY) !== text) {
    throw new Error(`citation: ${CITATION_COPY} differs from ${CITATION_SOURCE}`);
  }
  cached = buildCitation(parse(text), GITHUB_BASE);
  return cached;
}
