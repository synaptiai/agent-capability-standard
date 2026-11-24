// Write dist/documents.json: the capability ontology and every schema
// document under schemas/ (but the workflow catalogs), parsed by the core's
// own YAML loader through dist/wasm.js, so CoreContext needs no file system.
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const pkg = join(here, '..');
const repo = join(pkg, '..', '..');
const { AcsCore } = await import(pathToFileURL(join(pkg, 'dist', 'wasm.js')).href);
const core = await AcsCore.load(readFileSync(join(pkg, 'dist', 'acs_core.wasm')));

function* files(dir) {
  for (const name of readdirSync(dir).sort()) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* files(path);
    else yield path;
  }
}

const documents = {};
let ontology;
for (const path of files(join(repo, 'schemas'))) {
  const rel = relative(repo, path).split(sep).join('/');
  if (rel.startsWith('schemas/workflows/') || rel === 'schemas/workflow_catalog.yaml') continue;
  const text = readFileSync(path, 'utf8');
  let value;
  if (rel.endsWith('.json')) value = JSON.parse(text);
  else if (rel.endsWith('.yaml') || rel.endsWith('.yml')) value = core.parseYaml(text, 8 * 1024 * 1024);
  else continue;
  documents[rel] = value;
  if (rel === 'schemas/capability_ontology.yaml') ontology = value;
}
if (ontology === undefined) throw new Error('schemas/capability_ontology.yaml is missing');
writeFileSync(join(pkg, 'dist', 'documents.json'), JSON.stringify({ ontology, documents }));
console.log(`dist/documents.json: ${Object.keys(documents).length} documents`);
