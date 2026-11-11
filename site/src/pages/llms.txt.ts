// /llms.txt: every page's Markdown copy, grouped by section.
import { llmsTxt } from '../lib/agent-files';

export async function GET(): Promise<Response> {
  return new Response(await llmsTxt(), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
