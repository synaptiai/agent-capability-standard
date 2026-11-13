// /.well-known/ai-catalog.json: the predecessor of ard.json, with the same entries.
import { aiCatalog } from '../../lib/resource-catalog';

export function GET(): Response {
  return new Response(`${JSON.stringify(aiCatalog(), null, 2)}\n`, { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}
