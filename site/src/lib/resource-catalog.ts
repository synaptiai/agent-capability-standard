// The site's agent resources as an Agentic Resource Discovery manifest
// (ARD v0.91, ards-project/ard-spec spec/ard.md and
// spec/schemas/ard-entry.schema.json), served at /.well-known/ard.json, and
// as its predecessor ai-catalog.json (spec/schemas/ai-catalog.schema.json,
// specVersion "1.0"), served at /.well-known/ai-catalog.json.
//
// Each entry has a domain-anchored identifier urn:air:<host>:<name>, a
// displayName, a media type (`type`) and exactly one of url or data (here
// always url), plus a description and 2 to 5 representativeQueries, which
// the spec recommends. Media types are the ones ARD §3.3 lists where it lists
// one (MCP server card, agent skills); OpenAPI uses the type the OpenAPI
// Initiative registered, and the Markdown files text/markdown.
import { loadVersions } from '../data/versions';
import {
  AGENT_SKILLS_INDEX_PATH,
  DEVELOPERS_PATH,
  LLMS_TXT_PATH,
  MCP_SERVER_CARD_PATH,
  OPENAPI_PATH,
} from './agent-contract';
import { SITE_ORIGIN } from './origin';
import { PUBLISHER } from './structured-data';

export const CATALOG_HOST = new URL(SITE_ORIGIN).host;

export interface CatalogEntry {
  identifier: string;
  displayName: string;
  type: string;
  url: string;
  description: string;
  representativeQueries: string[];
  tags: string[];
  version?: string;
}

const entry = (name: string, rest: Omit<CatalogEntry, 'identifier'>): CatalogEntry => ({ identifier: `urn:air:${CATALOG_HOST}:${name}`, ...rest });

export function catalogEntries(): CatalogEntry[] {
  const v = loadVersions();
  const std = v.standard.current.version;
  return [
    entry('llms-txt', {
      displayName: 'Agent Capability Standard documentation (llms.txt)',
      type: 'text/markdown',
      url: `${SITE_ORIGIN}${LLMS_TXT_PATH}`,
      description: 'Index of the documentation for agents: when to use the standard, the agent interfaces, and a Markdown copy of every page by section.',
      representativeQueries: ['What does the Agent Capability Standard specify?', 'Which capability should a workflow step use?', 'Where is the Markdown version of the specification?'],
      tags: ['documentation', 'llms.txt', 'specification'],
      version: std,
    }),
    entry('openapi', {
      displayName: 'Agent Capability Standard data API',
      type: 'application/vnd.oai.openapi+json',
      url: `${SITE_ORIGIN}${OPENAPI_PATH}`,
      description: 'OpenAPI 3.1 description of the read-only JSON API with the capabilities, layers, edges, workflows, domain profiles and diagnostics.',
      representativeQueries: ['List the capabilities of the Agent Capability Standard as JSON', 'Get the input and output contract of a capability', 'Which workflows are in the reference catalog?'],
      tags: ['api', 'openapi', 'json', 'read-only'],
      version: v.ontology,
    }),
    entry('mcp-server', {
      displayName: 'Agent Capability Standard MCP server',
      type: 'application/mcp-server-card+json',
      url: `${SITE_ORIGIN}${MCP_SERVER_CARD_PATH}`,
      description: 'Server card of the read-only MCP server (Streamable HTTP) that searches and reads the standard.',
      representativeQueries: ['Search the Agent Capability Standard', 'Read the specification of the checkpoint capability', 'Explain validator diagnostic V102'],
      tags: ['mcp', 'search', 'documentation'],
    }),
    entry('agent-skills', {
      displayName: 'Agent Capability Standard skills',
      type: 'application/agent-skills+json',
      url: `${SITE_ORIGIN}${AGENT_SKILLS_INDEX_PATH}`,
      description: 'Agent skills discovery index (v0.2.0): every skill of the Claude Code plugin as a SKILL.md file with its SHA-256 digest.',
      representativeQueries: ['Install a skill that verifies an agent action', 'Find a skill for checkpoint and rollback', 'Which agent skills does this standard provide?'],
      tags: ['agent-skills', 'claude-code', 'skills'],
      version: v.plugin,
    }),
    entry('developers', {
      displayName: 'Agent Capability Standard for developers',
      type: 'text/markdown',
      url: `${SITE_ORIGIN}${DEVELOPERS_PATH}index.md`,
      description: 'How to use the data API, the MCP server and the Markdown copies of the documentation.',
      representativeQueries: ['How do I query the Agent Capability Standard from code?', 'Does the API need a key?'],
      tags: ['developers', 'documentation'],
    }),
  ];
}

/** /.well-known/ard.json: ARD needs only the entries array. */
export function ardManifest(): { entries: CatalogEntry[] } {
  return { entries: catalogEntries() };
}

/** /.well-known/ai-catalog.json: the same entries, with the version and host the ai-catalog schema has. */
export function aiCatalog(): { specVersion: '1.0'; host: { displayName: string; documentationUrl: string }; entries: CatalogEntry[] } {
  return {
    specVersion: '1.0',
    host: { displayName: PUBLISHER.name, documentationUrl: `${SITE_ORIGIN}/` },
    entries: catalogEntries(),
  };
}
