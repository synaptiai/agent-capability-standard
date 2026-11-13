// /.well-known/ard.json: the agent resources of the site (lib/resource-catalog.ts).
import { ardManifest } from '../../lib/resource-catalog';

export function GET(): Response {
  return new Response(`${JSON.stringify(ardManifest(), null, 2)}\n`, { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}
