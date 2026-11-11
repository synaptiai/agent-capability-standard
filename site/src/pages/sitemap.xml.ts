// /sitemap.xml: every HTML page in the route table. The 404 page, the
// Markdown copies and the text files are left out.
import { sitemapXml } from '../lib/agent-files';

export function GET(): Response {
  return new Response(sitemapXml(), { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
}
