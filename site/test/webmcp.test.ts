// Tests on the WebMCP tools (lib/webmcp.ts), registered on a fake
// document.modelContext and run against hand-written fixtures in
// fixtures/webmcp/: a fake fetch serves the fixture files at the data API and
// Markdown paths, and a fake Pagefind returns the fixture results.
// Expected values come from the fixtures and from the WebMCP draft
// (https://webmachinelearning.github.io/webmcp/, 12 November 2026): a tool
// name is 1 to 128 of [A-Za-z0-9_.-], description is required and not
// empty, inputSchema is a JSON Schema object.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  excerptText,
  markdownPath,
  webMcpTools,
  type ModelContext,
  type ModelContextTool,
  type PagefindApi,
  type PagefindResultData,
} from '../src/lib/webmcp';

const ORIGIN = 'https://acs.synapti.ai';
const fixture = (name: string) => readFileSync(path.join(__dirname, 'fixtures', 'webmcp', name), 'utf8');

/** Fixture files by the absolute URL a tool should fetch. */
const FILES: Record<string, string> = {
  [`${ORIGIN}/api/v1/capabilities/checkpoint.json`]: fixture('capability-checkpoint.json'),
  [`${ORIGIN}/api/v1/workflows/debug_code_change.json`]: fixture('workflow-debug_code_change.json'),
  [`${ORIGIN}/capabilities/detect/index.md`]: fixture('page-capabilities-detect.txt'),
};

function setup(opts: { pagefind?: PagefindApi | null } = {}) {
  const fetched: string[] = [];
  const fakeFetch = async (url: string) => {
    fetched.push(url);
    const body = FILES[url];
    return { ok: body !== undefined, status: body === undefined ? 404 : 200, text: async () => body ?? '<!doctype html>Not found' };
  };
  const results: PagefindResultData[] = JSON.parse(fixture('pagefind-checkpoint.json'));
  const searched: string[] = [];
  const pagefind: PagefindApi = {
    search: async (q) => {
      searched.push(q);
      return { results: results.map((r) => ({ data: async () => r })) };
    },
  };
  // A fake document.modelContext that records what is registered.
  const registered: ModelContextTool[] = [];
  const modelContext: ModelContext = {
    registerTool(tool) {
      registered.push(tool);
      return Promise.resolve();
    },
  };
  for (const tool of webMcpTools({ origin: ORIGIN, fetch: fakeFetch, loadPagefind: async () => (opts.pagefind === undefined ? pagefind : opts.pagefind) })) {
    modelContext.registerTool(tool);
  }
  const tool = (name: string) => {
    const t = registered.find((r) => r.name === name);
    if (!t) throw new Error(`${name} is not registered`);
    return t;
  };
  return { registered, tool, fetched, searched };
}

describe('WebMCP tool registration', () => {
  it('registers the four read-only tools by name', () => {
    expect(setup().registered.map((t) => t.name)).toEqual(['search_docs', 'read_capability', 'read_workflow', 'read_page_markdown']);
  });

  it('gives every tool a name the draft accepts, verb-led in snake_case', () => {
    for (const t of setup().registered) {
      expect(t.name, t.name).toMatch(/^[A-Za-z0-9_.-]{1,128}$/);
      expect(t.name, t.name).toMatch(/^(search|read)_[a-z]+(_[a-z]+)*$/);
    }
  });

  it('describes every tool and parameter, within the size an agent reads', () => {
    for (const t of setup().registered) {
      expect(t.description.length, t.name).toBeGreaterThanOrEqual(20);
      expect(t.description.length, t.name).toBeLessThanOrEqual(500);
      for (const [k, p] of Object.entries(t.inputSchema.properties)) {
        expect(typeof p.description, `${t.name}.${k}`).toBe('string');
        expect((p.description as string).length, `${t.name}.${k}`).toBeGreaterThanOrEqual(10);
        expect((p.description as string).length, `${t.name}.${k}`).toBeLessThanOrEqual(200);
      }
    }
  });

  it('gives every tool a JSON Schema object input with typed properties and required ones that exist', () => {
    for (const t of setup().registered) {
      const s = t.inputSchema;
      expect(s.type, t.name).toBe('object');
      expect(s.additionalProperties, t.name).toBe(false);
      expect(s.required.length, t.name).toBeGreaterThan(0);
      for (const r of s.required) expect(Object.keys(s.properties), t.name).toContain(r);
      for (const p of Object.values(s.properties)) {
        expect(['string', 'integer'], t.name).toContain(p.type);
        if (typeof p.pattern === 'string') expect(() => new RegExp(p.pattern as string)).not.toThrow();
      }
      // The schema survives JSON, as a browser passes it on to an agent.
      expect(JSON.parse(JSON.stringify(s))).toEqual(s);
    }
    const required = Object.fromEntries(setup().registered.map((t) => [t.name, t.inputSchema.required]));
    expect(required).toEqual({ search_docs: ['query'], read_capability: ['id'], read_workflow: ['id'], read_page_markdown: ['path'] });
  });

  it('marks every tool read-only and none consequential or untrusted', () => {
    for (const t of setup().registered) {
      expect(typeof t.execute, t.name).toBe('function');
      expect(t.annotations, t.name).toEqual({ readOnlyHint: true });
    }
  });
});

describe('WebMCP tool results', () => {
  it('read_capability returns the capability JSON from the data API', async () => {
    const { tool, fetched } = setup();
    const out = await tool('read_capability').execute({ id: 'checkpoint' });
    expect(out).toBe(fixture('capability-checkpoint.json'));
    expect(fetched).toEqual([`${ORIGIN}/api/v1/capabilities/checkpoint.json`]);
  });

  it('read_workflow returns the workflow JSON from the data API', async () => {
    const { tool, fetched } = setup();
    expect(await tool('read_workflow').execute({ id: 'debug_code_change' })).toBe(fixture('workflow-debug_code_change.json'));
    expect(fetched).toEqual([`${ORIGIN}/api/v1/workflows/debug_code_change.json`]);
  });

  it('read_page_markdown reads the Markdown copy for each way of naming the page', async () => {
    const { tool } = setup();
    const md = fixture('page-capabilities-detect.txt');
    for (const p of ['/capabilities/detect/', '/capabilities/detect', `${ORIGIN}/capabilities/detect/`, '/capabilities/detect/index.md', '/capabilities/detect.md', '/capabilities/detect/#intent']) {
      expect(await tool('read_page_markdown').execute({ path: p }), p).toBe(md);
    }
  });

  it('says what is missing, and where the list is, for an unknown id or page', async () => {
    const { tool } = setup();
    await expect(tool('read_capability').execute({ id: 'teleport' })).rejects.toThrow(/No capability "teleport".*\/api\/v1\/capabilities\.json/);
    await expect(tool('read_workflow').execute({ id: 'no_such_flow' })).rejects.toThrow(/No workflow "no_such_flow".*\/api\/v1\/workflows\.json/);
    await expect(tool('read_page_markdown').execute({ path: '/nowhere/' })).rejects.toThrow(/No page at "\/nowhere\/".*search_docs/);
  });

  it('refuses input outside the schema without fetching anything', async () => {
    const { tool, fetched } = setup();
    await expect(tool('read_capability').execute({ id: '../../secret' })).rejects.toThrow(/not a capability id/);
    await expect(tool('read_capability').execute({})).rejects.toThrow(/"id" must be a non-empty string/);
    await expect(tool('read_workflow').execute({ id: 'Debug Code' })).rejects.toThrow(/not a workflow id/);
    await expect(tool('read_page_markdown').execute({ path: 'https://example.com/capabilities/' })).rejects.toThrow(/not on this site/);
    await expect(tool('search_docs').execute({ query: '  ' })).rejects.toThrow(/"query" must be a non-empty string/);
    await expect(tool('search_docs').execute({ query: 'x', limit: 2.5 })).rejects.toThrow(/"limit" must be an integer/);
    expect(fetched).toEqual([]);
  });

  it('search_docs lists real matches with page and Markdown URLs, dropping loose ones', async () => {
    const { tool, searched } = setup();
    const out = await tool('search_docs').execute({ query: 'checkpoint' });
    expect(searched).toEqual(['checkpoint']);
    // The glossary result matched only a lone "c" and is left out.
    expect(out).toBe(
      [
        'Pages matching "checkpoint" (best first):',
        '',
        '1. Checkpoint (Capabilities)',
        '   URL: https://acs.synapti.ai/capabilities/checkpoint/',
        '   Markdown: https://acs.synapti.ai/capabilities/checkpoint/index.md',
        '   Excerpt: Create a checkpoint & restore it with rollback <state>.',
        '',
        '2. Standard v1.0.0 (Specification, Standard v1.0.0)',
        '   URL: https://acs.synapti.ai/spec/1.0.0/',
        '   Markdown: https://acs.synapti.ai/spec/1.0.0/index.md',
        '   Excerpt: A checkpoint must precede mutate.',
        '',
        '3. Debug code change (Workflows)',
        '   URL: https://acs.synapti.ai/workflows/debug-code-change/',
        '   Markdown: https://acs.synapti.ai/workflows/debug-code-change/index.md',
        '   Excerpt: Take a checkpoint before the fix.',
      ].join('\n'),
    );
  });

  it('search_docs returns no more than limit results', async () => {
    const out = await setup().tool('search_docs').execute({ query: 'checkpoint', limit: 1 });
    expect(out.match(/^\d+\. /gm)).toEqual(['1. ']);
    expect(out).toContain('1. Checkpoint (Capabilities)');
  });

  it('search_docs says so when nothing matches or the index cannot load', async () => {
    expect(await setup().tool('search_docs').execute({ query: 'zzzqqq' })).toBe('No pages match "zzzqqq".');
    await expect(setup({ pagefind: null }).tool('search_docs').execute({ query: 'checkpoint' })).rejects.toThrow(/search index could not load/);
  });
});

describe('WebMCP helpers', () => {
  it('turns a page path into its Markdown copy path', () => {
    expect(markdownPath('/', ORIGIN)).toBe('/index.md');
    expect(markdownPath('/spec/1.1.0/', ORIGIN)).toBe('/spec/1.1.0/index.md');
    expect(markdownPath('/spec/1.1.0', ORIGIN)).toBe('/spec/1.1.0/index.md');
    expect(markdownPath('/layers/verify/index.html', ORIGIN)).toBe('/layers/verify/index.md');
    expect(markdownPath('/layers/verify.md?x=1', ORIGIN)).toBe('/layers/verify/index.md');
  });

  it('turns a Pagefind excerpt into plain text', () => {
    expect(excerptText('a <mark>b</mark> &amp;&lt;c&gt; &quot;d&quot; &#39;e&#39;')).toBe('a b &<c> "d" \'e\'');
  });
});
