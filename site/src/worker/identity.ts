// The docs MCP server's identity, shared by server/discover, initialize and
// the server card, so the three never disagree.

import type { WorkerConfig } from './env';

export const MCP_PATH = '/mcp';
export const SERVER_NAME = 'ai.synapti.acs/mcp';
export const SERVER_TITLE = 'Agent Capability Standard docs';
/** At most 100 characters (server card schema). */
export const SERVER_DESCRIPTION = 'Search and read the Agent Capability Standard: capabilities, workflows and every documentation page.';

/** The modern (stateless) revision first, then the initialize-based ones this server also answers. */
export const MODERN_VERSIONS = ['2026-07-28'] as const;
export const LEGACY_VERSIONS = ['2025-11-25', '2025-06-18', '2025-03-26'] as const;
export const SUPPORTED_VERSIONS: readonly string[] = [...MODERN_VERSIONS, ...LEGACY_VERSIONS];

export const SERVER_CARD_SCHEMA = 'https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json';
export const SERVER_CARD_TYPE = 'application/mcp-server-card+json';

export function serverInfo(cfg: WorkerConfig) {
  return {
    name: SERVER_NAME,
    title: SERVER_TITLE,
    version: cfg.version,
    description: SERVER_DESCRIPTION,
    websiteUrl: `${cfg.origin}/`,
    icons: icons(cfg),
  };
}

function icons(cfg: WorkerConfig) {
  return [
    { src: `${cfg.origin}/favicon.svg`, mimeType: 'image/svg+xml', sizes: ['any'] },
    { src: `${cfg.origin}/favicon.png`, mimeType: 'image/png', sizes: ['32x32'] },
  ];
}

export function instructions(cfg: WorkerConfig): string {
  return [
    `This server gives read-only access to the Agent Capability Standard (current Standard version ${cfg.standardVersion}): its capability ontology, its reference workflows and every page of the documentation site at ${cfg.origin}/.`,
    'Start with search_standard to find the pages, capabilities and workflows that match a question.',
    'Then call read_capability with a capability id (for example "mutate") for its contract, risk and edges; read_workflow with a workflow id for its steps; or read_page with a page path from the search results for the Markdown text of that page. read_page returns a long page in parts (pass nextOffset as offset) or one section by its heading.',
    'Every tool only reads published files. Nothing here changes any state, and no tool needs authentication.',
  ].join(' ');
}

/** The server card (MCP Server Card extension, schema v1). It lists no tools: clients list them at run time. */
export function serverCard(cfg: WorkerConfig) {
  return {
    $schema: SERVER_CARD_SCHEMA,
    name: SERVER_NAME,
    title: SERVER_TITLE,
    description: SERVER_DESCRIPTION,
    version: cfg.version,
    websiteUrl: `${cfg.origin}/`,
    repository: { source: 'github', url: 'https://github.com/synaptiai/agent-capability-standard' },
    icons: icons(cfg),
    remotes: [{ type: 'streamable-http', url: `${cfg.origin}${MCP_PATH}`, supportedProtocolVersions: [...SUPPORTED_VERSIONS] }],
  };
}
