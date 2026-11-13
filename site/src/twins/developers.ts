// The Markdown copy of /developers/, from the same content module the page uses.
import { API_BASE, OPENAPI_PATH } from '../lib/api';
import {
  accessCaption,
  accessRoutes,
  ACCESS_FIG_TITLE,
  API_FACTS,
  catalogLine,
  curlExamples,
  DEVELOPERS_TITLE,
  developersDescription,
  endpointRows,
  endpointsCaption,
  ENDPOINTS_FIG_TITLE,
  ERRORS,
  LEAD,
  markdownExamples,
  MARKDOWN_LINES,
  MCP_CLAUDE_CODE,
  mcpCaption,
  mcpConfig,
  MCP_FIG_TITLE,
  MCP_LEAD,
  MCP_TOOLS,
  valuesText,
  VERSIONING,
  WEBMCP_LINES,
  type Example,
} from '../lib/developers';
import { SITE_ORIGIN } from '../lib/origin';
import { blocks, cell, code, fence, figure, table } from './md';
import type { Twin } from './types';

const at = (p: string) => `${SITE_ORIGIN}${p}`;
const list = (lines: readonly string[]) => lines.map((l) => `- ${l}`).join('\n');
const examples = (xs: Example[]) => fence('sh', xs.map((x) => `# ${x.what}\n${x.command}`).join('\n\n'));

export function developersTwin(): Twin {
  const routes = accessRoutes();
  const rows = endpointRows();
  const markdown = blocks(
    `# ${DEVELOPERS_TITLE}`,
    LEAD,
    figure(
      ACCESS_FIG_TITLE,
      accessCaption(routes),
      table(
        ['Route', 'Returns', 'Where', 'What it holds'],
        routes.map((r) => [cell(r.name), r.format, r.href ? `[${code(r.where)}](${at(r.href)})` : code(r.where), cell(r.line)]),
      ),
    ),
    '## JSON API',
    `The data of the Standard as static JSON files under ${code(`${API_BASE}/`)}, described by an OpenAPI 3.1 document at [${OPENAPI_PATH}](${at(OPENAPI_PATH)}).`,
    list(API_FACTS),
    figure(
      ENDPOINTS_FIG_TITLE,
      endpointsCaption(rows),
      table(
        ['Path', 'Operation', 'Returns', 'Files'],
        rows.map((r) => [`[${code(r.path)}](${at(r.href)})`, code(r.operationId), cell(r.summary), valuesText(r)]),
      ),
    ),
    '### Examples',
    examples(curlExamples()),
    '### Errors',
    ERRORS,
    '### Versioning and deprecation',
    list(VERSIONING),
    '### Discovery',
    catalogLine(),
    '## Markdown copies and llms.txt',
    list(MARKDOWN_LINES),
    examples(markdownExamples()),
    '## MCP server',
    MCP_LEAD,
    figure(MCP_FIG_TITLE, mcpCaption(), table(['Tool', 'What it does'], MCP_TOOLS.map((t) => [code(t.name), cell(t.does)]))),
    'Add it to Claude Code:',
    fence('sh', MCP_CLAUDE_CODE),
    'Or to a client that reads an MCP configuration file:',
    fence('json', mcpConfig()),
    '## WebMCP tools in the browser',
    list(WEBMCP_LINES),
  );
  return { title: DEVELOPERS_TITLE, description: developersDescription(), markdown };
}
