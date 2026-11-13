// The paths of the site's agent interfaces, as one table. llms.txt, the
// agents guide, the resource catalogs (/.well-known/ard.json and
// /.well-known/ai-catalog.json) and scripts/check-dist.mjs read it. This file
// has no imports, so the dist check can load it.
//
// Some of these are built outside this part of the site: the data API and its
// OpenAPI description and the developers page (static files), and the MCP
// server with its server card (served by the Pages function, never a file).
// PENDING_PATHS lists the static ones: the dist check accepts a link to one of
// them while no file serves it, so this part builds on its own. FUNCTION_PATHS
// lists the server card, which the check always accepts. The MCP endpoint
// itself answers only POST, so llms.txt names it as text and links the card.

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

/**
 * Paths other parts of the build produce, which may be missing from a build
 * of this part alone. Remove a path once it is built here.
 */
export const PENDING_PATHS: readonly string[] = [OPENAPI_PATH, API_INDEX_PATH, DEVELOPERS_PATH, `${DEVELOPERS_PATH}index.md`];

/** Paths that a link may name and the Pages function serves, never a file. */
export const FUNCTION_PATHS: readonly string[] = [MCP_SERVER_CARD_PATH];

/** Markdown files at the site root that are not a page's copy. */
export const ROOT_MARKDOWN: readonly string[] = [AGENTS_MD_PATH, LLMS_MD_PATH];

/** The name of each section's own llms.txt, at /<section>/llms.txt. */
export const SECTION_LLMS = 'llms.txt';
