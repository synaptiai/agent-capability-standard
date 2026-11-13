// /.well-known/agent-skills/index.json: the skills discovery index (lib/agent-skills.ts).
import { skillsIndex } from '../../../lib/agent-skills';

export function GET(): Response {
  return new Response(`${JSON.stringify(skillsIndex(), null, 2)}\n`, { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}
