// The reference core through its WebAssembly interface, for the tests: the
// module that `npm run build:wasm` writes to dist/, and a context of the
// repository's own schema documents, read in place.
import { AcsCore, type CoreContext, type Documents } from '../src/wasm.js';
import type { Json } from '../src/canonical.js';

const NODE_FS = 'node:fs/promises';

/** The module's bytes; a clear failure when it has not been built. */
async function moduleBytes(): Promise<Uint8Array> {
  const fs = (await import(/* @vite-ignore */ NODE_FS)) as { readFile(u: URL): Promise<Uint8Array> };
  const url = new URL('../dist/acs_core.wasm', import.meta.url);
  try {
    return await fs.readFile(url);
  } catch {
    throw new Error('dist/acs_core.wasm is missing: run `npm run build:wasm` first (it needs the wasm32-unknown-unknown target)');
  }
}

let cached: Promise<AcsCore> | undefined;

export function loadCore(): Promise<AcsCore> {
  cached ??= moduleBytes().then((bytes) => AcsCore.load(bytes));
  return cached;
}

const YAML = import.meta.glob<string>('../../../schemas/**/*.yaml', { eager: true, import: 'default', query: '?raw' });
const JSON_DOCS = import.meta.glob<Json>('../../../schemas/**/*.json', { eager: true, import: 'default' });

/** The repository's ontology and schema documents, parsed by the core, as
 * scripts/bundle-documents.mjs writes them. */
export function repositoryDocuments(core: AcsCore): Documents {
  const documents: Record<string, Json> = {};
  const key = (path: string) => path.replace(/^(\.\.\/)+/, '');
  for (const [path, text] of Object.entries(YAML)) {
    const rel = key(path);
    if (rel.startsWith('schemas/workflows/') || rel === 'schemas/workflow_catalog.yaml') continue;
    documents[rel] = core.parseYaml(text, 8 * 1024 * 1024);
  }
  for (const [path, value] of Object.entries(JSON_DOCS)) documents[key(path)] = value;
  const ontology = documents['schemas/capability_ontology.yaml'];
  if (ontology === undefined) throw new Error('no ontology');
  return { ontology, documents };
}

let context: CoreContext | undefined;

export async function repositoryContext(): Promise<CoreContext> {
  const core = await loadCore();
  context ??= core.context(repositoryDocuments(core));
  return context;
}
