// The four parts of the agent interface were built separately: the data API
// and the developers page, the discovery files, the worker with its MCP
// server, and the in-page WebMCP tools. These tests hold their shared names
// and paths to one another, so a rename in one part fails here instead of
// leaving another part pointing at nothing.
import { describe, expect, it } from 'vitest';
import * as contract from '../src/lib/agent-contract';
import { ENDPOINTS, MCP_TOOLS, MCP_URL } from '../src/lib/api';
import { API_BASE, DEVELOPERS_URL, OPENAPI_PATH } from '../src/lib/api-paths';
import { WEBMCP_TOOLS } from '../src/lib/developers';
import { SITE_ORIGIN } from '../src/lib/origin';
import { capabilityPath, webMcpTools, workflowPath } from '../src/lib/webmcp';
import { MCP_PATH } from '../src/worker/identity';
import { TOOLS } from '../src/worker/tools';

const stubDeps = {
  origin: SITE_ORIGIN,
  fetch: async () => ({ ok: false, status: 404, text: async () => '' }),
  loadPagefind: async () => null,
};

describe('agent interface contract', () => {
  it('names the MCP server tools on the developers page exactly as the worker defines them', () => {
    expect(MCP_TOOLS.map((t) => t.name).sort()).toEqual(TOOLS.map((t) => t.name).sort());
  });

  it('names the WebMCP tools on the developers page exactly as each page registers them', () => {
    expect([...WEBMCP_TOOLS]).toEqual(webMcpTools(stubDeps).map((t) => t.name));
  });

  it('puts the MCP endpoint at the same path in the worker, the developers page and the discovery files', () => {
    expect(MCP_PATH).toBe(contract.MCP_PATH);
    expect(MCP_URL).toBe(`${SITE_ORIGIN}${contract.MCP_PATH}`);
  });

  it('agrees on the OpenAPI, API index and developers paths', () => {
    expect(contract.OPENAPI_PATH).toBe(OPENAPI_PATH);
    expect(contract.API_INDEX_PATH).toBe(`${API_BASE}/index.json`);
    expect(contract.DEVELOPERS_PATH).toBe(DEVELOPERS_URL);
    expect(ENDPOINTS.map((e) => e.path)).toContain(contract.API_INDEX_PATH);
  });

  it('reads capabilities and workflows in WebMCP from paths the data API defines', () => {
    const paths = ENDPOINTS.map((e) => e.path);
    expect(paths).toContain(capabilityPath('{id}'));
    expect(paths).toContain(workflowPath('{id}'));
  });
});
