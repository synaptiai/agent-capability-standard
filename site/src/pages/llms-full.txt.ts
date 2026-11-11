// /llms-full.txt: the current Standard, the capabilities and the workflows in one file.
import { llmsFullTxt } from '../lib/agent-files';

export async function GET(): Promise<Response> {
  return new Response(await llmsFullTxt(), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
