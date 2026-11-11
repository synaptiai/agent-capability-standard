// /robots.txt: allow everything and point at the sitemap.
import { robotsTxt } from '../lib/agent-files';

export function GET(): Response {
  return new Response(robotsTxt(), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
