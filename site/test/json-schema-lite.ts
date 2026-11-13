// A small JSON Schema checker for the tests of the data API: it checks the
// built JSON files against the response schemas of the OpenAPI document. It
// knows only the keywords those schemas use, and throws on any other, so a
// schema cannot pass by using a keyword this checker would ignore.
type Schema = Record<string, unknown>;

const KNOWN = new Set([
  '$ref', 'type', 'properties', 'required', 'additionalProperties', 'items', 'enum', 'const',
  'pattern', 'format', 'minimum', 'minLength', 'description',
]);

function typeOf(v: unknown): string {
  if (v === null) return 'null';
  if (Array.isArray(v)) return 'array';
  if (typeof v === 'number') return Number.isInteger(v) ? 'integer' : 'number';
  return typeof v;
}

function typeMatches(want: string, v: unknown): boolean {
  const t = typeOf(v);
  return want === t || (want === 'number' && t === 'integer');
}

/** Resolve a local `#/a/b` reference against the root document. */
export function resolveRef(root: Schema, ref: string): Schema {
  if (!ref.startsWith('#/')) throw new Error(`json-schema-lite: only local refs are supported, got ${ref}`);
  let node: unknown = root;
  for (const part of ref.slice(2).split('/')) {
    if (typeof node !== 'object' || node === null || !(part in node)) throw new Error(`json-schema-lite: ${ref} does not resolve`);
    node = (node as Schema)[part];
  }
  return node as Schema;
}

/** Problems with `value` against `schema`, one line each with its JSON path. */
export function validate(root: Schema, schema: Schema, value: unknown, at = '$', out: string[] = []): string[] {
  for (const k of Object.keys(schema)) if (!KNOWN.has(k)) throw new Error(`json-schema-lite: unsupported keyword ${k} at ${at}`);
  if (typeof schema.$ref === 'string') return validate(root, resolveRef(root, schema.$ref), value, at, out);
  if (schema.type !== undefined) {
    const types = Array.isArray(schema.type) ? (schema.type as string[]) : [schema.type as string];
    if (!types.some((t) => typeMatches(t, value))) {
      out.push(`${at}: is ${typeOf(value)}, expected ${types.join(' or ')}`);
      return out;
    }
  }
  if (schema.enum !== undefined && !(schema.enum as unknown[]).some((e) => e === value)) out.push(`${at}: ${JSON.stringify(value)} is not in the enum`);
  if ('const' in schema && schema.const !== value) out.push(`${at}: ${JSON.stringify(value)} is not ${JSON.stringify(schema.const)}`);
  if (typeof value === 'string') {
    if (typeof schema.pattern === 'string' && !new RegExp(schema.pattern, 'u').test(value)) out.push(`${at}: "${value}" does not match ${schema.pattern}`);
    if (typeof schema.minLength === 'number' && value.length < schema.minLength) out.push(`${at}: shorter than ${schema.minLength}`);
    if (schema.format === 'uri' && !/^https?:\/\/\S+$/.test(value)) out.push(`${at}: "${value}" is not an absolute http(s) URI`);
  }
  if (typeof value === 'number' && typeof schema.minimum === 'number' && value < schema.minimum) out.push(`${at}: ${value} is below ${schema.minimum}`);
  if (Array.isArray(value) && schema.items !== undefined) {
    value.forEach((v, i) => validate(root, schema.items as Schema, v, `${at}[${i}]`, out));
  }
  if (typeOf(value) === 'object') {
    const obj = value as Record<string, unknown>;
    const props = (schema.properties ?? {}) as Record<string, Schema>;
    for (const r of (schema.required ?? []) as string[]) if (!(r in obj)) out.push(`${at}: missing ${r}`);
    for (const [k, v] of Object.entries(obj)) {
      if (k in props) validate(root, props[k]!, v, `${at}.${k}`, out);
      else if (schema.additionalProperties === false) out.push(`${at}: ${k} is not in the schema`);
      else if (typeof schema.additionalProperties === 'object') validate(root, schema.additionalProperties as Schema, v, `${at}.${k}`, out);
    }
  }
  return out;
}

/** Every `$ref` string in a document. */
export function refsIn(node: unknown, out: string[] = []): string[] {
  if (Array.isArray(node)) for (const v of node) refsIn(v, out);
  else if (typeof node === 'object' && node !== null) {
    for (const [k, v] of Object.entries(node)) {
      if (k === '$ref' && typeof v === 'string') out.push(v);
      else refsIn(v, out);
    }
  }
  return out;
}
