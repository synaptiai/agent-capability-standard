// The Markdown plugins, run through the build pipeline on real sources. The
// expected values are read off the source files named in each case.
import { describe, expect, it } from 'vitest';
import { readRepoFile } from '../src/lib/repo';
import { KEYWORD_SOURCES, unroutedKeywordSources } from '../src/lib/markdown';
import { checkHtml } from '../src/plugins/remark-html-allowlist';
import { shortDescription, type PageMeta } from '../src/plugins/remark-page-meta';
import { KEYWORDS, markKeywords } from '../src/plugins/rehype-keywords';
import { tableLabel } from '../src/plugins/rehype-tables';
import { standardVersions } from '../src/data/versions';
import { pageHead } from '../src/lib/page-head';
import { DESCRIPTIONS, routeForSource, type Route } from '../src/lib/routes';
import { sectionLines } from './independent';
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
    // The Status line ends in a hard break (two spaces).
    expect(readRepoFile(source).split('\n')).toContain('**Status:** Accepted  ');
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
    expect(readRepoFile(source).split('\n')).toContain('**Document Status**: Normative');
    const { page } = await pageOf(source);
    expect(page.documentStatus).toBe('Normative');
    expect(page.title).toBe('Extension Governance: Adding a New Capability');
  });

  it('ignores a Status line that is not directly after the H1 (README.md)', async () => {
    // README.md has a Status line well below its H1 (line 468 at 9945a39).
    const at = readRepoFile('README.md').split('\n').findIndex((l) => /^\*\*Status:\*\* /.test(l));
    expect(at).toBeGreaterThan(2);
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

describe('shortDescription', () => {
  // The limit routes.ts holds hand-written descriptions to (200 characters).
  it('stays within the limit when it cuts at a word and adds an ellipsis', () => {
    const words = Array.from({ length: 60 }, (_, i) => `word${i}`).join(' ');
    const solid = 'x'.repeat(300);
    for (const text of [words, solid, `${'a'.repeat(198)} bbbbbbbb`]) {
      const d = shortDescription(text);
      expect(d.length, d).toBeLessThanOrEqual(200);
      expect(d.endsWith('...')).toBe(true);
    }
  });

  it('cuts at a sentence end when there is one past character 40', () => {
    const text = `${'A sentence that is long enough to count. '.repeat(3)}${'more words '.repeat(30)}`;
    expect(shortDescription(text)).toBe('A sentence that is long enough to count. '.repeat(3).trim());
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

  it('rejects attributes on the allowed elements, except open on details', () => {
    // An event handler on any allowed element would run script on the site,
    // while GitHub strips it, so the source looks harmless in review.
    expect(checkHtml('<details open>')).toEqual([]);
    expect(checkHtml('<br/>')).toEqual([]);
    expect(checkHtml('<br />')).toEqual([]);
    expect(checkHtml('<details open ontoggle="alert(document.domain)">')).toEqual(['<details> may carry only open, found: open, ontoggle']);
    expect(checkHtml('<summary onclick="x()">')).toEqual(['<summary> may carry no attributes, found: onclick']);
    expect(checkHtml('<br onmouseover=x()>')).toEqual(['<br> may carry no attributes, found: onmouseover']);
    expect(checkHtml('<sup style="color:red">')).toEqual(['<sup> may carry no attributes, found: style']);
    expect(checkHtml('<sub class="x">')).toEqual(['<sub> may carry no attributes, found: class']);
    expect(checkHtml('<a name="x" onclick="y()">')).toEqual(['<a> may carry only name or id, found: name, onclick']);
  });

  it('does not let a malformed comment hide an element', () => {
    // A browser ends each of these comments earlier than the regex would, so
    // the element after it is live HTML.
    for (const html of ['<!--><details ontoggle=alert(1)>-->', '<!---><details ontoggle=alert(1)>-->', '<!-- --!><details ontoggle=alert(1)>-->']) {
      expect(checkHtml(html), html).not.toEqual([]);
    }
  });

  it('reads comments and tags in one pass, as a browser does', () => {
    // A "<!--" inside a tag, or inside a quoted attribute value, is part of
    // the tag, so it must not hide the tag or what follows it.
    expect(checkHtml('<details open ontoggle=alert(1) <!-- -->')).not.toEqual([]);
    expect(checkHtml('<details><a name="<!--"><details open ontoggle=alert(1)>-->')).toContain(
      '<details> may carry only open, found: open, ontoggle',
    );
    // A tag with no closing ">" is not let through unread.
    expect(checkHtml('<details open ontoggle=alert(1) x="')).toEqual(['unclosed or malformed tag: <details open ontoggle=alert(1) x="']);
  });

  it('fails the build on an event handler hidden after a comment opener through the real pipeline', async () => {
    const text = `${readRepoFile('docs/FAQ.md')}\n\n<details open ontoggle=alert(1) <!-- -->\n`;
    await expect(renderRepoFile('docs/FAQ.md', text)).rejects.toThrow(/remark-html-allowlist/);
  });

  it('fails the build on an event handler through the real pipeline', async () => {
    const text = `${readRepoFile('docs/FAQ.md')}\n\n<details open ontoggle="alert(1)">\n<summary>x</summary>\n</details>\n`;
    await expect(renderRepoFile('docs/FAQ.md', text)).rejects.toThrow(/<details> may carry only open/);
  });

  it('fails the build on a bare <id> in prose', async () => {
    const text = `${readRepoFile('docs/FAQ.md')}\n\nThe message reads <id> failed.\n`;
    await expect(renderRepoFile('docs/FAQ.md', text)).rejects.toThrow(/<id> is not an allowed HTML element/);
  });
});

describe('rehype-keywords', () => {
  it('uses the keyword list of spec §1.2 Notation', () => {
    // The lines of spec/STANDARD-v1.1.0.md from the "### 1.2 Notation" heading to the next heading.
    const notation = sectionLines(readRepoFile('spec/STANDARD-v1.1.0.md'), /^### 1\.2 Notation$/).join('\n');
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
    // docs/proposals/OASF_SAFETY_EXTENSIONS.md (six at 9945a39).
    const source = 'docs/proposals/OASF_SAFETY_EXTENSIONS.md';
    const inSource = readRepoFile(source).split('\n').filter((l) => l.startsWith('> **Note:**')).length;
    expect(inSource).toBeGreaterThan(1);
    const { html } = await pageOf(source);
    // The label leads with the same glyph the generated Callout component uses (visual spec 3.10.3).
    expect(html.match(/<div class="callout callout--note" role="note"><p class="callout__label"><svg [^>]*data-glyph="note"[^>]*>(?:(?!<\/svg>)[\s\S])*<\/svg> Note<\/p>/g)).toHaveLength(inSource);
    expect(html).not.toContain('<strong>Note:</strong>');
  });

  it('accepts the GitHub alert form and leaves plain quotes alone', async () => {
    const text = `${readRepoFile('docs/FAQ.md')}\n\n> [!WARNING]\n> Careful.\n\n> Just a quote.\n`;
    const { html } = await pageOf('docs/FAQ.md', text);
    expect(html).toMatch(/<div class="callout callout--warning" role="note"><p class="callout__label"><svg [^>]*data-glyph="warning"[^>]*>(?:(?!<\/svg>)[\s\S])*<\/svg> Warning<\/p>\s*<p>Careful\.<\/p>/);
    expect(html).toMatch(/<blockquote>\s*<p>Just a quote\.<\/p>/);
  });
});

describe('page title and description', () => {
  const headOf = async (source: string) => pageHead(routeForSource(source)!, (await pageOf(source)).page);

  it('prefers a route description over the derived one', () => {
    const page: PageMeta = {
      title: 'Paper',
      description: 'A. Author a@example.org',
      meta: [],
      version: null,
      status: null,
      documentStatus: null,
      date: null,
    };
    const route: Route = { source: 'x.md', url: '/x/', section: 'background', order: 0, template: 'prose', title: 'X' };
    expect(pageHead(route, page).description).toBe('A. Author a@example.org');
    expect(pageHead({ ...route, description: 'What the paper covers.' }, page)).toEqual({
      title: 'Paper',
      headTitle: 'Paper',
      description: 'What the paper covers.',
    });
  });

  it('gives the Grounded Agency paper its route description', async () => {
    const head = await headOf('docs/GROUNDED_AGENCY.md');
    expect(head.description).toBe(DESCRIPTIONS['docs/GROUNDED_AGENCY.md']);
    expect(head.description).not.toContain('@');
  });

  it('keeps the derived description where the route has none', async () => {
    const { page } = await pageOf('docs/QUICKSTART.md');
    expect((await headOf('docs/QUICKSTART.md')).description).toBe(page.description);
  });

  it('tells the versions of the Standard apart by their Version line', async () => {
    const versions = standardVersions();
    expect(versions.length).toBeGreaterThan(1);
    const heads = await Promise.all(versions.map((v) => headOf(v.source)));
    // Same H1 in every version; the breadcrumb title stays the H1.
    expect(new Set(heads.map((h) => h.title)).size).toBe(1);
    heads.forEach((h, i) => {
      expect(h.headTitle).toBe(`${h.title}, version ${versions[i]!.version}`);
      expect(h.description).toMatch(new RegExp(`^Version ${versions[i]!.version.replace(/\./g, '\\.')}\\. `));
    });
    expect(new Set(heads.map((h) => h.headTitle)).size).toBe(versions.length);
  });
});

describe('rehype-tables', () => {
  it('wraps every table of a file in a focusable, labelled region', async () => {
    // Expected: one wrapper per GFM delimiter row outside code fences in the source.
    const source = 'spec/STANDARD-v1.1.0.md';
    let fenced = false;
    const inSource = readRepoFile(source)
      .split('\n')
      .filter((l) => {
        if (/^\s*(```|~~~)/.test(l)) fenced = !fenced;
        return !fenced && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/.test(l) && l.includes('|');
      }).length;
    expect(inSource).toBeGreaterThan(1);
    const { html } = await pageOf(source);
    expect(html.match(/<table/g)).toHaveLength(inSource);
    expect(html.match(/<div class="table-wrap" role="region" tabindex="0" aria-label="[^"]+"><table>/g)).toHaveLength(inSource);
  });

  it('names a table from the heading before it, and leaves its display alone', async () => {
    const text = `${readRepoFile('docs/FAQ.md')}\n\n## Odd *table* here\n\n| a | b |\n|---|---|\n| 1 | 2 |\n`;
    const { html } = await pageOf('docs/FAQ.md', text);
    expect(html).toContain('<div class="table-wrap" role="region" tabindex="0" aria-label="Table: Odd table here"><table>');
  });
});

describe('tableLabel', () => {
  it('prefers the caption, then the heading, then a plain word', () => {
    expect(tableLabel(' Gates  of step 2 ', 'Steps')).toBe('Gates of step 2');
    expect(tableLabel(null, ' Layer  architecture ')).toBe('Table: Layer architecture');
    expect(tableLabel('', null)).toBe('Table');
  });
});

describe('rehype-task-lists', () => {
  it('names each checkbox with its own item text, not its nested items', async () => {
    const md = '# T\n\n- [ ] Verify the checkpoint exists\n- [x] Log the `mutation` result\n  - [ ] Nested step\n';
    const { html } = await pageOf('docs/FAQ.md', md);
    const labels = [...html.matchAll(/<input type="checkbox"[^>]*aria-label="([^"]*)"/g)].map((m) => m[1]);
    // Written by hand from the three items above.
    expect(labels).toEqual(['Verify the checkpoint exists', 'Log the mutation result', 'Nested step']);
    expect(html).not.toMatch(/<input type="checkbox"(?![^>]*aria-label)[^>]*>/);
  });

  it('cuts a long item at a word', async () => {
    const { taskLabel } = await import('../src/plugins/rehype-task-lists');
    const long = 'word '.repeat(40).trim(); // 199 characters
    const out = taskLabel(long);
    expect(out.endsWith('word…')).toBe(true);
    expect(out.length).toBeLessThanOrEqual(121);
  });
});

describe('rehype-tables labels', () => {
  it('gives tables under the same heading distinct region names', async () => {
    const md = '# T\n\n## Fields\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n| c | d |\n|---|---|\n| 3 | 4 |\n';
    const { html } = await pageOf('docs/FAQ.md', md);
    const labels = [...html.matchAll(/class="table-wrap"[^>]*aria-label="([^"]*)"/g)].map((m) => m[1]);
    expect(labels).toEqual(['Table: Fields', 'Table: Fields (2)']);
  });
});
