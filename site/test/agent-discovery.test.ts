// Tests on the built site's discovery files: the front matter of the
// Markdown copies, the sitemap's lastmod dates, robots.txt, the home page's
// JSON-LD and og:type, the resource catalogs, the agent skills index, the
// agents guide and the about, contact and privacy pages. The suite builds the
// site into its own temporary directory, as dist.test.ts does.
//
// Expected values come from git, the repository's files and the published
// formats (ARD v0.91 and ai-catalog 1.0 from ards-project/ard-spec, the Agent
// Skills Discovery RFC v0.2.0), not from the modules that build the files.
import { stripTags } from '../src/lib/strip';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import path from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { repoText, standardFileVersions } from './independent';

const ORIGIN = 'https://acs.synapti.ai';
let work = '';
let dist = '';

beforeAll(() => {
  work = mkdtempSync(path.join(process.cwd(), 'node_modules', '.acs-discovery-test-'));
  dist = path.join(work, 'dist');
  execFileSync('npx', ['astro', 'build', '--force', '--outDir', dist], {
    cwd: process.cwd(),
    stdio: 'pipe',
    env: { ...process.env, ACS_ASTRO_CACHE_DIR: path.join(work, 'cache') },
  });
}, 300_000);

afterAll(() => {
  if (work) rmSync(work, { recursive: true, force: true });
});

const read = (f: string) => readFileSync(path.join(dist, f), 'utf8');
const repoRoot = path.resolve(process.cwd(), '..');
const gitDate = (...paths: string[]) =>
  execFileSync('git', ['log', '-1', '--format=%cI', '--', ...paths], { cwd: repoRoot, encoding: 'utf8' }).trim();

/** Every index.md under dist, the review pages aside, as URL paths of their pages. */
function copyDirs(dir = '', out: string[] = []): string[] {
  for (const e of readdirSync(path.join(dist, dir), { withFileTypes: true })) {
    if (e.isDirectory() && dir === '' && (e.name === '_review' || e.name === '.well-known')) continue;
    if (e.isDirectory()) copyDirs(path.posix.join(dir, e.name), out);
    else if (e.name === 'index.md') out.push(dir === '' ? '/' : `/${dir}/`);
  }
  return out.sort();
}

/** Front matter fields of a served copy, parsed as the JSON strings they are written as. */
function frontmatter(md: string): Record<string, string> | null {
  const m = /^---\n([\s\S]*?)\n---\n\n/.exec(md);
  if (!m) return null;
  return Object.fromEntries(m[1]!.split('\n').map((l) => [l.slice(0, l.indexOf(':')), JSON.parse(l.slice(l.indexOf(':') + 1).trim()) as string]));
}

describe('Markdown copies', () => {
  it('open with front matter (title, canonical URL), then a top-level heading, and balance their code fences', () => {
    const bad: string[] = [];
    for (const d of copyDirs()) {
      const md = read(`${d.slice(1)}index.md`);
      const fm = frontmatter(md);
      if (!fm) {
        bad.push(`${d}: no front matter`);
        continue;
      }
      if (!fm.title) bad.push(`${d}: no title`);
      if (fm.canonical !== `${ORIGIN}${d}`) bad.push(`${d}: canonical ${fm.canonical}`);
      const body = md.replace(/^---\n[\s\S]*?\n---\n\n/, '');
      if (!body.startsWith('# ')) bad.push(`${d}: body does not start with a top-level heading`);
      // CommonMark: a fence closes on a line of the same character, at least as long.
      let open: string | null = null;
      for (const line of body.split('\n')) {
        const f = /^ {0,3}(`{3,}|~{3,})/.exec(line)?.[1];
        if (!f) continue;
        if (open === null) open = f;
        else if (f[0] === open[0] && f.length >= open.length && /^ {0,3}[`~]+\s*$/.test(line)) open = null;
      }
      if (open !== null) bad.push(`${d}: an unclosed ${open} fence`);
    }
    expect(bad).toEqual([]);
  });

  it('date the current Standard\'s copy and its sitemap entry by the last commit to its source', () => {
    const v = standardFileVersions()[0]!;
    const want = gitDate(`spec/STANDARD-v${v}.md`);
    expect(want).not.toBe('');
    expect(frontmatter(read(`spec/${v}/index.md`))!.last_updated).toBe(want);
    expect(read('sitemap.xml')).toContain(`<loc>${ORIGIN}/spec/${v}/</loc><lastmod>${want}</lastmod>`);
  });

  it('date a capability page by the later of its skill and the ontology', () => {
    const skill = gitDate('skills/verify/SKILL.md');
    const onto = gitDate('schemas/capability_ontology.yaml');
    const want = Date.parse(skill) > Date.parse(onto) ? skill : onto;
    expect(frontmatter(read('capabilities/verify/index.md'))!.last_updated).toBe(want);
  });

  it('give every committed page a lastmod in the sitemap', () => {
    const xml = read('sitemap.xml');
    const urls = [...xml.matchAll(/<url>([\s\S]*?)<\/url>/g)].map((m) => m[1]!);
    expect(urls.length).toBe(copyDirs().length);
    // A page built from files not yet committed has none; every other has one.
    const without = urls.filter((u) => !u.includes('<lastmod>')).map((u) => /<loc>([^<]+)/.exec(u)![1]!);
    const uncommitted = execFileSync('git', ['status', '--porcelain'], { cwd: repoRoot, encoding: 'utf8' }).trim();
    if (uncommitted === '') expect(without).toEqual([]);
  });
});

describe('robots.txt', () => {
  it('allows every crawler, names the AI search and user agents with the same rule, and lists the sitemap', () => {
    const text = read('robots.txt');
    const groups = text.split(/\n\s*\n/).filter((g) => /User-agent:/i.test(g));
    for (const g of groups) expect(g.split('\n').filter((l) => /^(Allow|Disallow):/i.test(l))).toEqual(['Allow: /']);
    for (const bot of ['*', 'OAI-SearchBot', 'Claude-SearchBot', 'PerplexityBot', 'ChatGPT-User', 'Claude-User', 'Perplexity-User']) {
      expect(text).toContain(`User-agent: ${bot}\n`);
    }
    expect(text).toContain(`Sitemap: ${ORIGIN}/sitemap.xml`);
  });
});

describe('home page metadata', () => {
  const graph = () => {
    const m = /<script type="application\/ld\+json">([\s\S]*?)<\/script>/.exec(read('index.html'));
    return (JSON.parse(m![1]!) as { '@graph': Record<string, unknown>[] })['@graph'];
  };
  const plugin = () => JSON.parse(repoText('.claude-plugin/plugin.json')) as { version: string; license: string };

  it('describes the site, its publisher, the standard and the plugin in JSON-LD', () => {
    const g = graph();
    const byType = (t: string) => g.find((n) => n['@type'] === t)!;
    expect(byType('WebSite').url).toBe(`${ORIGIN}/`);
    const org = byType('Organization');
    expect(org.name).toBe('Synapti');
    expect(org.url).toBe('https://synapti.ai');
    expect(org.sameAs).toContain('https://github.com/synaptiai');
    expect(byType('SoftwareApplication').sameAs).toEqual(['https://github.com/synaptiai/agent-capability-standard', 'https://skills.sh/synaptiai/agent-capability-standard']);
    const contact = org.contactPoint as Record<string, string>;
    expect(contact.contactType).toBeTruthy();
    expect(contact.url).toMatch(/^https:\/\/github\.com\/synaptiai\/[^/]+\/issues$/);
    expect(contact).not.toHaveProperty('email');
    expect(contact).not.toHaveProperty('telephone');
    const app = byType('SoftwareApplication');
    expect(app.softwareVersion).toBe(plugin().version);
    expect(app.offers).toMatchObject({ '@type': 'Offer', price: '0', priceCurrency: 'USD' });
    expect(app.license).toContain(plugin().license);
    expect(String(app.keywords).length).toBeGreaterThan(0);
    const std = byType('CreativeWork');
    expect(std.version).toBe(standardFileVersions()[0]);
  });

  it('sets og:type website on the home page and article on a docs page, and links the resource catalogs', () => {
    expect(read('index.html')).toContain('<meta property="og:type" content="website">');
    expect(read('capabilities/verify/index.html')).toContain('<meta property="og:type" content="article">');
    expect(read('index.html')).toMatch(/<link rel="ard"[^>]*href="\/\.well-known\/ard\.json"/);
    expect(read('index.html')).toMatch(/<link rel="ai-catalog"[^>]*href="\/\.well-known\/ai-catalog\.json"/);
  });
});

describe('resource catalogs', () => {
  // The identifier pattern of ard-entry.schema.json and ai-catalog.schema.json.
  const URN = /^urn:air:[a-zA-Z0-9.-]+(:[a-zA-Z0-9._-]+)+$/;
  // Built by other parts of the site (the API) or served by the Pages function (the server card).
  const ELSEWHERE = ['/openapi.json', '/.well-known/mcp/server-card.json', '/developers/index.md'];

  for (const file of ['.well-known/ard.json', '.well-known/ai-catalog.json']) {
    it(`${file}: every entry has a domain-anchored urn:air id, a name, a media type and exactly one of url or data`, () => {
      const doc = JSON.parse(read(file)) as { specVersion?: string; entries: Record<string, unknown>[] };
      if (file.endsWith('ai-catalog.json')) {
        expect(doc.specVersion).toBe('1.0');
        expect(Object.keys(doc).sort()).toEqual(['entries', 'host', 'specVersion']);
      }
      expect(doc.entries.length).toBe(5);
      for (const e of doc.entries) {
        expect(e.identifier).toMatch(URN);
        expect(String(e.identifier).startsWith('urn:air:acs.synapti.ai:')).toBe(true);
        expect(typeof e.displayName).toBe('string');
        expect(e.type).toMatch(/^[a-z]+\/[a-z0-9.+-]+$/);
        expect(('url' in e ? 1 : 0) + ('data' in e ? 1 : 0)).toBe(1);
        const q = e.representativeQueries as string[];
        expect(q.length).toBeGreaterThanOrEqual(2);
        expect(q.length).toBeLessThanOrEqual(5);
        const p = String(e.url).slice(ORIGIN.length);
        if (!ELSEWHERE.includes(p)) expect(existsSync(path.join(dist, p)), p).toBe(true);
      }
    });
  }
});

describe('agent skills index', () => {
  it('lists every skills/*/SKILL.md with its front matter name and the SHA-256 of the served bytes, which equal the source', () => {
    const index = JSON.parse(read('.well-known/agent-skills/index.json')) as { $schema: string; skills: { name: string; type: string; description: string; url: string; digest: string }[] };
    expect(index.$schema).toBe('https://schemas.agentskills.io/discovery/0.2.0/schema.json');
    const sources = execFileSync('git', ['ls-files', 'skills/*/SKILL.md'], { cwd: repoRoot, encoding: 'utf8' }).trim().split('\n');
    expect(index.skills.length).toBe(sources.length);
    const names = new Set<string>();
    for (const source of sources) {
      const text = repoText(source);
      const name = /^name:\s*(\S+)\s*$/m.exec(text.split('\n---')[0]!)![1]!;
      const entry = index.skills.find((s) => s.name === name)!;
      expect(entry, source).toBeDefined();
      names.add(name);
      expect(entry.type).toBe('skill-md');
      expect(entry.url).toBe(`/.well-known/agent-skills/${name}/SKILL.md`);
      expect(entry.name).toMatch(/^[a-z0-9]+(-[a-z0-9]+)*$/);
      expect(entry.description.length).toBeGreaterThan(0);
      expect(entry.description.length).toBeLessThanOrEqual(1024);
      const served = readFileSync(path.join(dist, entry.url));
      expect(entry.digest).toBe(`sha256:${createHash('sha256').update(served).digest('hex')}`);
      expect(served.equals(readFileSync(path.join(repoRoot, source)))).toBe(true);
    }
    expect(names.size).toBe(sources.length);
  });

  it('serves the skill copies and other Markdown files as text/markdown', () => {
    const headers = read('_headers');
    expect(headers).toMatch(/^\/\*\.md\n\s+Content-Type: text\/markdown/m);
  });
});

describe('agents guide and llms.md', () => {
  it('serve Markdown that starts with a top-level heading', () => {
    expect(read('agents.md').startsWith('# ')).toBe(true);
    expect(read('llms.md')).toBe(read('llms.txt'));
    expect(read('agents.md')).toContain(`${ORIGIN}/capabilities/index.md`);
  });
});

/** `html` without its script elements, found case-insensitively by a scan (no regex tag filter). */
function withoutScripts(html: string): string {
  let out = html;
  for (let i = out.toLowerCase().indexOf('<script'); i !== -1; i = out.toLowerCase().indexOf('<script')) {
    const end = out.toLowerCase().indexOf('</script', i);
    const close = end === -1 ? -1 : out.indexOf('>', end);
    out = close === -1 ? out.slice(0, i) : out.slice(0, i) + out.slice(close + 1);
  }
  return out;
}

describe('about, contact and privacy pages', () => {
  it('each have at least 500 characters of text in the main element, and a Markdown copy', () => {
    for (const p of ['about', 'contact', 'privacy']) {
      const html = read(`${p}/index.html`);
      const main = /<main[\s\S]*?<\/main>/.exec(html)![0];
      const text = stripTags(withoutScripts(main), ' ').replace(/\s+/g, ' ').trim();
      expect(text.length, p).toBeGreaterThanOrEqual(500);
      expect(existsSync(path.join(dist, p, 'index.md'))).toBe(true);
    }
  });

  it('match the built site on the privacy page claims: no cookies, nothing loaded from another site but the overview badges', () => {
    const offsite: string[] = [];
    for (const d of copyDirs()) {
      const html = read(`${d.slice(1)}index.html`);
      expect(html, d).not.toMatch(/document\.cookie/);
      for (const m of html.matchAll(/<script\b[^>]*\ssrc="([^"]+)"/g)) expect(m[1]!.startsWith('/'), d).toBe(true);
      // Elements that load a resource: src on any element, href on <link> other than canonical and alternate.
      for (const m of html.matchAll(/<[a-z]+\b[^>]*\ssrc="((?:https?:)?\/\/[^"]+)"/g)) offsite.push(`${d} ${new URL(m[1]!, ORIGIN).host}`);
      for (const m of html.matchAll(/<link\b(?![^>]*rel="(?:canonical|alternate)")[^>]*\shref="((?:https?:)?\/\/[^"]+)"/g)) offsite.push(`${d} ${new URL(m[1]!, ORIGIN).host}`);
    }
    expect([...new Set(offsite)]).toEqual(['/start/overview/ img.shields.io']);
    for (const f of readdirSync(path.join(dist, '_astro')).filter((x) => x.endsWith('.css'))) {
      expect(read(`_astro/${f}`), f).not.toMatch(/url\(\s*["']?(?:https?:)?\/\/|@import/);
    }
    // The privacy page names the badges' host.
    expect(read('privacy/index.html')).toContain('img.shields.io');
  });
});
