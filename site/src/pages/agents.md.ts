// /agents.md: how an agent should use this site.
import { agentsMd } from '../lib/agent-files';

export function GET(): Response {
  return new Response(agentsMd(), { headers: { 'Content-Type': 'text/markdown; charset=utf-8' } });
}
