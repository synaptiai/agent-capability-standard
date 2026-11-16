/**
 * The reference core (validator, executor, YAML loader, expressions and
 * domain profiles) in process, through its WebAssembly JSON interface
 * (`core/src/wasm.rs`): JSON in, JSON out, over three C-ABI exports. This
 * entry is the package's only way to check and apply domain profiles
 * (Standard 1.2.0 section 5.21): one implementation, the core's, serves
 * Rust, Python and TypeScript.
 *
 * Memory protocol: a request is encoded as UTF-8 into a buffer from
 * `acs_alloc(len)`; `acs_call(ptr, len)` returns a pointer to a new buffer
 * that holds a 4-byte little-endian length `n` and then `n` bytes of JSON;
 * both buffers are released with `acs_free` and their lengths.
 */
import type { CapabilityId, DeclaredFlags } from './ontology.js';
import type { Json } from './canonical.js';
import type {
  Action,
  CoreResponse,
  CoreVersion,
  Diagnostic,
  ProfileFlags,
  ProfilePolicy,
  Report,
  Snapshot,
} from './core-types.js';

export type * from './core-types.js';

/** A request the core refused, or a trapped instance. */
export class CoreError extends Error {
  /** `bad_request`, `unknown_op`, `unknown_handle`, `load`, `yaml`,
   * `start`, `submit`, `restore`, `run`, `too_large`, or `trapped` (the
   * instance can no longer be used: load a new one). */
  readonly kind: string;
  readonly diagnostics: Json[] | undefined;

  constructor(kind: string, message: string, diagnostics?: Json[]) {
    super(`${kind}: ${message}`);
    this.name = 'CoreError';
    this.kind = kind;
    this.diagnostics = diagnostics;
  }
}

interface Exports {
  memory: WebAssembly.Memory;
  acs_alloc(len: number): number;
  acs_free(ptr: number, len: number): void;
  acs_call(ptr: number, len: number): number;
}

type Answer = { ok: unknown } | { error: { kind: string; message: string; diagnostics?: Json[] } };

/** The bundled documents (`dist/documents.json`): the ontology and the
 * schema documents a contract or workflow may reference. */
export interface Documents {
  ontology: Json;
  documents: Record<string, Json>;
}

const NODE_FS = 'node:fs/promises';

async function readBytes(url: URL): Promise<ArrayBuffer | Uint8Array> {
  if (url.protocol === 'file:') {
    // Node: read the file. A variable specifier keeps bundlers and the
    // type-checker from requiring Node.
    const fs = (await import(/* @vite-ignore */ NODE_FS)) as {
      readFile(path: URL): Promise<Uint8Array>;
    };
    return fs.readFile(url);
  }
  const response = await fetch(url);
  if (!response.ok) throw new CoreError('load', `cannot fetch ${url.href}: ${response.status}`);
  return response.arrayBuffer();
}

const registry =
  typeof FinalizationRegistry === 'undefined'
    ? undefined
    : new FinalizationRegistry<() => void>((release) => {
        try {
          release();
        } catch {
          // The instance is gone or broken: nothing to release.
        }
      });

/** One instance of the core. */
export class AcsCore {
  private readonly exports: Exports;
  private broken = false;
  private readonly encoder = new TextEncoder();
  private readonly decoder = new TextDecoder('utf-8', { fatal: true });

  private constructor(exports: Exports) {
    this.exports = exports;
  }

  /**
   * Instantiate the core. `source`: the module's bytes, a compiled module,
   * or its URL; the default is `acs_core.wasm` beside this file.
   */
  static async load(source?: BufferSource | WebAssembly.Module | URL): Promise<AcsCore> {
    let module: WebAssembly.Module;
    if (source instanceof WebAssembly.Module) {
      module = source;
    } else {
      const bytes =
        source === undefined || source instanceof URL
          ? await readBytes(source ?? new URL('./acs_core.wasm', import.meta.url))
          : source;
      module = await WebAssembly.compile(bytes as BufferSource);
    }
    const instance = await WebAssembly.instantiate(module, {});
    return new AcsCore(instance.exports as unknown as Exports);
  }

  /** Send one request; the answer's `ok`, or a thrown {@link CoreError}. */
  call<T>(op: string, args: Record<string, unknown> = {}): T {
    if (this.broken) throw new CoreError('trapped', 'this instance trapped; load a new one');
    const request = this.encoder.encode(JSON.stringify({ op, ...args }));
    const { memory, acs_alloc, acs_free, acs_call } = this.exports;
    let text: string;
    try {
      const ptr = acs_alloc(request.length);
      new Uint8Array(memory.buffer, ptr, request.length).set(request);
      const out = acs_call(ptr, request.length);
      // The memory may have grown during the call: read through fresh views.
      const n = new DataView(memory.buffer).getUint32(out, true);
      text = this.decoder.decode(new Uint8Array(memory.buffer, out + 4, n));
      acs_free(ptr, request.length);
      acs_free(out, 4 + n);
    } catch (e) {
      if (e instanceof WebAssembly.RuntimeError) {
        this.broken = true;
        throw new CoreError('trapped', e.message);
      }
      throw e;
    }
    const answer = JSON.parse(text) as Answer;
    if ('error' in answer) {
      throw new CoreError(answer.error.kind, answer.error.message, answer.error.diagnostics);
    }
    return answer.ok as T;
  }

  version(): CoreVersion {
    return this.call<CoreVersion>('version');
  }

  /** Parse YAML (one document) with the core's hardened loader. */
  parseYaml(text: string, maxBytes?: number): Json {
    return this.call<Json>('yaml.parse', maxBytes === undefined ? { text } : { text, max_bytes: maxBytes });
  }

  /** Parse a catalog file's text: the catalog and the version its
   * `# Standard version:` header declares (or null), the pair a host
   * passes on (section 11.5). */
  parseCatalog(text: string): { catalog: Json; header: string | null } {
    return this.call('catalog.parse', { text });
  }

  /** A validation context: the given ontology and documents, or the
   * bundled ones (`dist/documents.json`, which {@link loadDocuments}
   * reads). */
  context(init: Documents): CoreContext {
    const { context } = this.call<{ context: number }>('context.new', {
      ontology: init.ontology,
      documents: init.documents,
    });
    return new CoreContext(this, context);
  }

  /** @internal Release a handle (best effort). */
  release(op: string, args: Record<string, unknown>): void {
    if (!this.broken) this.call(op, args);
  }
}

/** The bundled documents beside this file (`documents.json`). */
export async function loadDocuments(url?: URL): Promise<Documents> {
  const bytes = await readBytes(url ?? new URL('./documents.json', import.meta.url));
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  return JSON.parse(new TextDecoder().decode(view)) as Documents;
}

/** Another catalog of a catalog set (section 5.1.1), with the version its
 * header declares, or null (`parseCatalog` returns both). */
export interface SetCatalog {
  catalog: Json;
  header: string | null;
}

/** The members of a catalog set besides the catalog (sections 5.1.1 and
 * 5.15.1): a run is restored with the ones it started with. */
export interface SetArgs {
  /** The other catalogs of the catalog's set: qualified `invoke` targets
   * resolve over them. */
  catalogs?: SetCatalog[];
  /** Agent manifests: a `delegate` step's targets are checked against them
   * (section 5.15.2). */
  agents?: Json[];
}

/** The `catalogs` and `agents` members of a request, when given. */
function setMembers(o: SetArgs): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (o.catalogs !== undefined) out.catalogs = o.catalogs;
  if (o.agents !== undefined) out.agents = o.agents;
  return out;
}

/** How a run starts (section 5.19.2). */
export interface StartArgs extends SetArgs {
  catalog: Json;
  workflow: string;
  inputs?: Record<string, Json>;
  /** The version the catalog's header declares, or null (section 11.5);
   * `parseCatalog` returns it. Required. */
  header: string | null;
  runId: string;
  attendance?: 'attended' | 'unattended';
  nowMs: number;
  actorIdentity?: Json;
  records?: 'approvals' | 'actions';
  /** Domain profiles the host applies (section 5.21). */
  profiles?: Json[];
  /** Where each of their loading warnings goes (a misspelled top-level
   * member is W604, and ignored; section 5.21.4): `console.warn` by
   * default, one line with the code, the message and the suggestion. */
  onWarning?: (warning: Diagnostic) => void;
  grounding?: Json[];
  destinations?: string[][];
}

/** One line for a profile's loading warning. */
function warningText(d: Diagnostic): string {
  return `acs-core start: ${d.code} ${d.severity}: ${d.message}${d.suggestion !== undefined ? ` (${d.suggestion})` : ''}`;
}

/** How a saved run continues (section 5.19.4). */
export interface RestoreArgs extends SetArgs {
  catalog: Json;
  snapshot: Snapshot;
  keyHex?: string;
  /** The actor the host continues the run for (section 5.17): a principal
   * other than the run's is refused, as is any actor for a run started
   * without one. */
  actorIdentity?: Json;
}

/** How a run that ended `deferred` is resumed (section 5.14.1). */
export interface ResumeArgs {
  /** The run's attendance from now on; attended by default. */
  attendance?: 'attended' | 'unattended';
  nowMs: number;
  /** Who carries the run on (section 5.17); the run's actor when left out. */
  actorIdentity?: Json;
}

/** A validation context: an ontology and its documents, loaded once. */
export class CoreContext {
  constructor(
    private readonly core: AcsCore,
    readonly handle: number,
  ) {
    registry?.register(this, () => core.release('context.drop', { context: handle }), this);
  }

  /** Validate a catalog (section 10). `header` is required: the version its
   * header declares, or null. `catalogs` and `agents` as for `start`. */
  validate(catalog: Json, opts: { header: string | null; profiles?: Json[] } & SetArgs): Report {
    if (!opts || !('header' in opts)) {
      throw new CoreError('bad_request', 'header is required: the version the catalog header declares, or null');
    }
    return this.core.call<Report>('validate', {
      context: this.handle,
      catalog,
      header: opts.header,
      profiles: opts.profiles ?? [],
      ...setMembers(opts),
    });
  }

  /** The diagnostics of loading domain profiles (section 5.21.2). */
  checkProfiles(profiles: Json[]): Report {
    const { diagnostics } = this.core.call<{ diagnostics: Report['diagnostics'] }>('profile.check', {
      context: this.handle,
      profiles,
    });
    return { diagnostics, suggestions: [] };
  }

  /** The effective flags of a step or call of `capability` under
   * `profiles` (section 5.21.3). Throws when the profiles have an error. */
  profileFlags(profiles: Json[], capability: CapabilityId, declared?: DeclaredFlags): ProfileFlags {
    return this.core.call<ProfileFlags>('profile.flags', {
      context: this.handle,
      profiles,
      capability,
      declared: declared ?? null,
    });
  }

  /** The rules `profiles` put in force besides flags (section 5.21.3).
   * Throws when the profiles have an error. */
  profilePolicy(profiles: Json[]): ProfilePolicy {
    return this.core.call<ProfilePolicy>('profile.policy', { context: this.handle, profiles });
  }

  /** Every capability's contracts with each `$ref` resolved. */
  contracts(): Json {
    return this.core.call<Json>('context.contracts', { context: this.handle });
  }

  /** Start a run (section 5.19.2). Each warning of loading its profiles
   * goes to `o.onWarning` (section 5.21.4). */
  start(o: StartArgs): CoreRun {
    if (!('header' in o) || (o.header !== null && typeof o.header !== 'string')) {
      throw new CoreError(
        'bad_request',
        "options.header is required: the version the catalog's header declares (parseCatalog returns it), or null",
      );
    }
    const options: Record<string, unknown> = {
      run_id: o.runId,
      now_ms: o.nowMs,
      header: o.header,
      attendance: o.attendance ?? 'attended',
    };
    if (o.actorIdentity !== undefined) options.actor_identity = o.actorIdentity;
    if (o.records !== undefined) options.records = o.records;
    if (o.profiles !== undefined) options.profiles = o.profiles;
    if (o.grounding !== undefined) options.grounding = o.grounding;
    if (o.destinations !== undefined) options.destinations = o.destinations;
    Object.assign(options, setMembers(o));
    const { run, warnings } = this.core.call<{ run: number; warnings: Diagnostic[] }>('run.start', {
      context: this.handle,
      catalog: o.catalog,
      workflow: o.workflow,
      inputs: o.inputs ?? {},
      options,
    });
    const started = new CoreRun(this.core, run);
    const report = o.onWarning ?? ((d: Diagnostic) => console.warn(warningText(d)));
    for (const w of warnings) report(w);
    return started;
  }

  /** Continue a saved run against the same catalog (section 5.19.4). */
  restore(o: RestoreArgs): CoreRun {
    const { run } = this.core.call<{ run: number }>('run.restore', {
      context: this.handle,
      catalog: o.catalog,
      snapshot: o.snapshot,
      key_hex: o.keyHex ?? null,
      actor_identity: o.actorIdentity ?? null,
      ...setMembers(o),
    });
    return new CoreRun(this.core, run);
  }

  /** Release the context; a run it started keeps running. */
  dispose(): void {
    registry?.unregister(this);
    this.core.release('context.drop', { context: this.handle });
  }
}

/** One run of the reference executor. */
export class CoreRun {
  constructor(
    private readonly core: AcsCore,
    readonly handle: number,
  ) {
    registry?.register(this, () => core.release('run.drop', { run: handle }), this);
  }

  /** The pending action, or the terminal one once the run has finished. */
  next(): Action {
    return this.core.call<Action>('run.next', { run: this.handle });
  }

  /** Answer the pending action `id`. */
  submit(id: number, response: CoreResponse, nowMs: number): void {
    this.core.call('run.submit', { run: this.handle, id, response, now_ms: nowMs });
  }

  /** Tell the run the time; whether it changed the run (section 5.19.2): a
   * new action is pending, or the run ended. */
  tick(nowMs: number): boolean {
    return this.core.call<{ changed: boolean }>('run.tick', { run: this.handle, now_ms: nowMs }).changed;
  }

  /** The earliest time at which a tick changes the run, or null (section 5.19.3). */
  wakeAt(): number | null {
    return this.core.call<number | null>('run.wake_at', { run: this.handle });
  }

  /** The run's identifier (section 5.19.2). */
  runId(): string {
    return this.core.call<string>('run.run_id', { run: this.handle });
  }

  /** Cancel the run (section 5.19.5): it ends `Failed` with R408. Throws
   * (kind `run`) when it has ended otherwise than `deferred`. */
  cancel(reason: string, nowMs: number): void {
    this.core.call('run.cancel', { run: this.handle, reason, now_ms: nowMs });
  }

  /** Resume a run that ended `deferred` (section 5.14.1), as the same run.
   * Throws (kind `run`) when it did not end deferred, or its state does not
   * keep what resuming needs. Resume one saved state once. */
  resume(o: ResumeArgs): void {
    this.core.call('run.resume', {
      run: this.handle,
      attendance: o.attendance ?? 'attended',
      now_ms: o.nowMs,
      actor_identity: o.actorIdentity ?? null,
    });
  }

  finished(): boolean {
    return this.core.call<boolean>('run.finished', { run: this.handle });
  }

  /** The trace events the run holds; with `since`, those whose `seq` is at
   * least `since`. */
  trace(since?: number): Json[] {
    return this.core.call<Json[]>('run.trace', { run: this.handle, since: since ?? null });
  }

  /** The `seq` the run's next trace event gets. */
  traceSeq(): number {
    return this.core.call<number>('run.trace_seq', { run: this.handle });
  }

  /** Take the trace out of the run's state (section 5.19.4); `seq` goes on. */
  takeTrace(): Json[] {
    return this.core.call<Json[]>('run.take_trace', { run: this.handle });
  }

  /** Take the settled action records out of the run's state (section 5.19.4). */
  takeRecords(): Json[] {
    return this.core.call<Json[]>('run.take_records', { run: this.handle });
  }

  /** The chain heads over what was taken (section 5.19.4), each empty while
   * nothing was taken. */
  takenSha256(): { records: string; trace: string } {
    return this.core.call<{ records: string; trace: string }>('run.taken_sha256', { run: this.handle });
  }

  /** The run's record (section 5.19.8), or null while the run goes on. */
  runRecord(): Json {
    return this.core.call<Json>('run.run_record', { run: this.handle });
  }

  actionRecords(): Json[] {
    return this.core.call<Json[]>('run.action_records', { run: this.handle });
  }

  /** The run's state, with an HMAC under the key when given. */
  snapshot(keyHex?: string): Snapshot {
    return this.core.call<Snapshot>('run.snapshot', { run: this.handle, key_hex: keyHex ?? null });
  }

  dispose(): void {
    registry?.unregister(this);
    this.core.release('run.drop', { run: this.handle });
  }
}
