// The paths of the site's agent interfaces, as one table. llms.txt, the
// agents guide, the resource catalogs (/.well-known/ard.json and
// /.well-known/ai-catalog.json) and scripts/check-dist.mjs read it. This file
// has no imports, so the dist check can load it.
//
// The MCP server and its server card are served by the site's worker, never
// as files. FUNCTION_PATHS lists the server card, which the dist check
// accepts as a link target with no file. The MCP endpoint itself answers only
// POST, so llms.txt names it as text and links the card.

/** The MCP endpoint (Streamable HTTP, read-only). */
export const MCP_PATH = '/mcp';
export const OPENAPI_PATH = '/openapi.json';
export const API_INDEX_PATH = '/api/v1/index.json';
export const MCP_SERVER_CARD_PATH = '/.well-known/mcp/server-card.json';
export const DEVELOPERS_PATH = '/developers/';
export const AGENT_SKILLS_INDEX_PATH = '/.well-known/agent-skills/index.json';
export const AGENT_SKILLS_DIR = '/.well-known/agent-skills/';
export const ARD_PATH = '/.well-known/ard.json';
export const AI_CATALOG_PATH = '/.well-known/ai-catalog.json';
export const AGENTS_MD_PATH = '/agents.md';
export const LLMS_MD_PATH = '/llms.md';
export const LLMS_TXT_PATH = '/llms.txt';
export const LLMS_FULL_PATH = '/llms-full.txt';

/** Paths that a link may name and the Pages function serves, never a file. */
export const FUNCTION_PATHS: readonly string[] = [MCP_SERVER_CARD_PATH];

/** Markdown files at the site root that are not a page's copy. */
export const ROOT_MARKDOWN: readonly string[] = [AGENTS_MD_PATH, LLMS_MD_PATH];

/** The name of each section's own llms.txt, at /<section>/llms.txt. */
export const SECTION_LLMS = 'llms.txt';
