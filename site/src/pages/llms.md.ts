// /llms.md: llms.txt as a Markdown file, for agents that look for one.
import { llmsMd } from '../lib/agent-files';

export async function GET(): Promise<Response> {
  return new Response(await llmsMd(), { headers: { 'Content-Type': 'text/markdown; charset=utf-8' } });
}
