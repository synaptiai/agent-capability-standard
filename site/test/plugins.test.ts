// The Markdown plugins, run through the build pipeline on real sources. The
// expected values are read off the source files named in each case.
import { describe, expect, it } from 'vitest';
import { readRepoFile } from '../src/lib/repo';
import { KEYWORD_SOURCES, unroutedKeywordSources } from '../src/lib/markdown';
import { checkHtml } from '../src/plugins/remark-html-allowlist';
import type { PageMeta } from '../src/plugins/remark-page-meta';
import { KEYWORDS, markKeywords } from '../src/plugins/rehype-keywords';
import { renderRepoFile } from './pipeline';

async function pageOf(source: string, text?: string): Promise<{ page: PageMeta; html: string }> {
  const r = await renderRepoFile(source, text);
  return { page: r.metadata.frontmatter.page as PageMeta, html: r.code };
}

describe('remark-page-meta', () => {
  it('reads the spec header block (spec/STANDARD-v1.1.0.md lines 1-10)', async () => {
    const { page, html } = await pageOf('spec/STANDARD-v1.1.0.md');
    expect(page.title).toBe('Standard: Agent Capability Ontology + Workflow DSL');
    expect(page.version).toBe('1.1.0');
    expect(page.date).toBe('2026-10-28');
    // The Status value spans lines 4-8 and holds two links.
    expect(page.status).toMatch(/^Candidate Standard — accepted by RFC-0003 and RFC-0004; the reference validator/);
    expect(page.status).toMatch(/identity resolution or F505$/);
    expect(page.meta.map((m) => m.key)).toEqual(['Version', 'Status', 'Date', 'Supersedes']);
    // Kept in the body as a definition list, links rewritten.
    expect(html).toContain('<dl class="page-meta"><div><dt>Version</dt><dd>1.1.0</dd></div>');
    expect(html).toContain('<a href="/rfcs/0003/">RFC-0003</a>');
    // The H1 stays, with its own id.
    expect(html).toMatch(/<h1 id="standard-agent-capability-ontology--workflow-dsl">/);
  });

  it('reads an RFC header written with hard breaks (RFC-0001 lines 2-4)', async () => {
    const source = 'spec/RFC-0001-agent-capability-ontology-and-workflow-dsl.md';
    expect(readRepoFile(source).split('\n')[1]).toBe('**Status:** Accepted  ');
    const { page } = await pageOf(source);
    expect(page.status).toBe('Accepted');
    expect(page.meta).toEqual([
      { key: 'Status', value: 'Accepted' },
      { key: 'Target', value: 'Standard v1.0.0' },
      { key: 'Date', value: '2026-01-24' },
    ]);
  });

  it('reads a Document Status written with the colon outside the bold', async () => {
    const source = 'docs/methodology/EXTENSION_GOVERNANCE.md';
    expect(readRepoFile(source).split('\n')[2]).toBe('**Document Status**: Normative');
    const { page } = await pageOf(source);
    expect(page.documentStatus).toBe('Normative');
    expect(page.title).toBe('Extension Governance: Adding a New Capability');
  });

  it('ignores a Status line that is not directly after the H1 (README.md:468)', async () => {
    expect(readRepoFile('README.md').split('\n')[467]).toMatch(/^\*\*Status:\*\* Candidate Standard v1\.1\.0/);
    const { page } = await pageOf('README.md');
    expect(page.status).toBeNull();
    expect(page.meta).toEqual([]);
  });

  it('skips the badge row when choosing a description (README.md)', async () => {
    const { page } = await pageOf('README.md');
    expect(page.description).not.toMatch(/Claude Code Plugin License/);
    expect(page.description!.length).toBeLessThanOrEqual(203);
  });

  it('takes a SKILL.md title and description from its frontmatter', async () => {
    const text = readRepoFile('skills/debug-workflow/SKILL.md');
    const name = /^name: (.+)$/m.exec(text)![1];
    const { page } = await pageOf('skills/debug-workflow/SKILL.md');
    expect(page.title).toBe(name);
    expect(page.description).toMatch(/^Execute the Debug Code Change workflow/);
  });
});

describe('remark-repo-links errors', () => {
  it('names the source line of a bad link in a file with frontmatter', async () => {
    const source = 'skills/detect/SKILL.md';
    const text = `${readRepoFile(source).replace(/\n+$/, '')}\n\nSee [nothing](./missing.md).\n`;
    const line = text.split('\n').length - 1;
    await expect(renderRepoFile(source, text)).rejects.toThrow(`skills/detect/SKILL.md:${line}: ./missing.md -> `);
  });
});

describe('remark-html-allowlist', () => {
  it('allows the elements the sources use', () => {
    // docs/research/analysis/validator-engine-disagreements-1.0.md:339-340
    expect(checkHtml('<details>\n<summary>The other 24 cases</summary>')).toEqual([]);
    expect(checkHtml('<a name="legacy"></a>')).toEqual([]);
    expect(checkHtml('<!-- note -->')).toEqual([]);
  });

  it('rejects anything else', () => {
    expect(checkHtml('<object>')).toEqual(['<object> is not an allowed HTML element']);
    expect(checkHtml('<a href="x">')).toEqual(['<a> may carry only name or id, found: href']);
    expect(checkHtml('<script>alert(1)</script>')).toHaveLength(2);
  });

  it('fails the build on a bare <id> in prose', async () => {
    const text = `${readRepoFile('docs/FAQ.md')}\n\nThe message reads <id> failed.\n`;
    await expect(renderRepoFile('docs/FAQ.md', text)).rejects.toThrow(/<id> is not an allowed HTML element/);
  });
});

describe('rehype-keywords', () => {
  it('uses the keyword list of spec §1.2 Notation', () => {
    // spec/STANDARD-v1.1.0.md:45-47
    const notation = readRepoFile('spec/STANDARD-v1.1.0.md').split('\n').slice(44, 47).join('\n');
    const listed = [...notation.matchAll(/\*\*([A-Z ]+)\*\*/g)].map((m) => m[1]).sort();
    expect(Object.keys(KEYWORDS).sort()).toEqual(listed);
  });

  it('keeps MUST NOT as one span and leaves lowercase and identifiers alone', () => {
    const out = markKeywords('It MUST NOT run; it may run; MAY_X and MUSTARD stay.');
    const spans = out!.filter((n) => n.type === 'element');
    expect(spans).toHaveLength(1);
    expect(spans[0]).toMatchObject({ properties: { className: ['kw', 'kw--must'] }, children: [{ value: 'MUST NOT' }] });
  });

  it('names every keyword source that has no route', () => {
    expect(unroutedKeywordSources(KEYWORD_SOURCES)).toEqual([]);
    expect(unroutedKeywordSources([...KEYWORD_SOURCES, 'spec/NO_SUCH_FILE.md'])).toEqual(['spec/NO_SUCH_FILE.md']);
    // The three companions listed by path in markdown.ts are in the set.
    for (const s of ['spec/CONFORMANCE.md', 'spec/EDGE_TYPES.md', 'spec/SECURITY.md']) expect(KEYWORD_SOURCES.has(s)).toBe(true);
  });

  it('marks the spec and RFCs but not prose pages', async () => {
    expect(KEYWORD_SOURCES.has('spec/STANDARD-v1.1.0.md')).toBe(true);
    expect(KEYWORD_SOURCES.has('spec/RFC-0002-agent-reliability-profile.md')).toBe(true);
    expect(KEYWORD_SOURCES.has('docs/FAQ.md')).toBe(false);
    const spec = (await pageOf('spec/STANDARD-v1.1.0.md')).html;
    expect(spec).toContain('<span class="kw kw--must">MUST NOT</span>');
    // Headings and code are skipped: no keyword span inside a pre block.
    expect(spec).not.toMatch(/<pre[^>]*>(?:(?!<\/pre>)[\s\S])*class="kw /);
  });
});

describe('rehype-callouts', () => {
  it('turns every > **Note:** block of a file into a callout', async () => {
    // docs/proposals/OASF_SAFETY_EXTENSIONS.md has six, at lines 259, 261, 272, 374, 564 and 603.
    const source = 'docs/proposals/OASF_SAFETY_EXTENSIONS.md';
    const inSource = readRepoFile(source).split('\n').filter((l) => l.startsWith('> **Note:**')).length;
    expect(inSource).toBe(6);
    const { html } = await pageOf(source);
    expect(html.match(/<div class="callout callout--note" role="note"><p class="callout__label">Note<\/p>/g)).toHaveLength(6);
    expect(html).not.toContain('<strong>Note:</strong>');
  });

  it('accepts the GitHub alert form and leaves plain quotes alone', async () => {
    const text = `${readRepoFile('docs/FAQ.md')}\n\n> [!WARNING]\n> Careful.\n\n> Just a quote.\n`;
    const { html } = await pageOf('docs/FAQ.md', text);
    expect(html).toMatch(/<div class="callout callout--warning" role="note"><p class="callout__label">Warning<\/p>\s*<p>Careful\.<\/p>/);
    expect(html).toMatch(/<blockquote>\s*<p>Just a quote\.<\/p>/);
  });
});
