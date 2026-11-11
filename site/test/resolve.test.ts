// The link resolver against real links in the repository. Each case names the
// file the link is written in (checked below, so a removed link fails loudly),
// and the expected URL comes from the site design, not from the
// route table:
// - page URLs: design notes, "ia-home" section 3 and "review" section 1
//   (/start/, /guides/skills/, /rfcs/0001/ form, /spec/<version>/);
// - directory pages: design notes, "pipeline" section 3, "Directory links";
// - GitHub URLs for YAML, LICENSE, excluded files and other directories:
//   plan, recommended default 6, and design notes "pipeline" section 4.
import { describe, expect, it } from 'vitest';
import { anchorsOf, bodyLineOffset, computeAnchors } from '../src/lib/anchors';
import { repoResolver, SITE_ORIGIN } from '../src/lib/links';
import { GITHUB_BASE, readRepoFile, TRACKED_FILES } from '../src/lib/repo';
import { createResolver, type Resolution } from '../src/lib/resolve';
import { renderRepoFile } from './pipeline';

const resolve = repoResolver();
const blob = (p: string) => `${GITHUB_BASE}/blob/main/${p}`;
const tree = (p: string) => `${GITHUB_BASE}/tree/main/${p}`;

/** Assert the link is really written in that file. */
function written(file: string, href: string): void {
  expect(readRepoFile(file), `${file} should contain ](${href})`).toContain(`](${href})`);
}

function ok(r: Resolution): { kind: string; url: string; anchorChecked: boolean } {
  if (!r.ok) throw new Error(`expected a resolved link, got: ${r.reason}`);
  return { kind: r.kind, url: r.url, anchorChecked: r.anchorChecked };
}

describe('links to Markdown pages', () => {
  it('rewrites a sibling .md link to its route', () => {
    written('spec/STANDARD-v1.1.0.md', 'RFC-0003-orchestration-extensions.md');
    expect(ok(resolve('spec/STANDARD-v1.1.0.md', 'RFC-0003-orchestration-extensions.md'))).toEqual({
      kind: 'route',
      url: '/rfcs/0003/',
      anchorChecked: false,
    });
  });

  it('keeps and checks the anchor of an anchored link', () => {
    written('docs/guides/RUNNING_WORKFLOWS.md', '../../spec/STANDARD-v1.1.0.md#5-workflow-dsl');
    expect(ok(resolve('docs/guides/RUNNING_WORKFLOWS.md', '../../spec/STANDARD-v1.1.0.md#5-workflow-dsl'))).toEqual({
      kind: 'route',
      url: '/spec/1.1.0/#5-workflow-dsl',
      anchorChecked: true,
    });
    written('README.md', 'skills/README.md#composed-skills-6');
    expect(ok(resolve('README.md', 'skills/README.md#composed-skills-6')).url).toBe('/guides/skills/#composed-skills-6');
  });

  it('resolves three levels up from a nested research document', () => {
    const href = '../../../spec/STANDARD-v1.1.0.md#appendix-c-changes-from-100';
    written('docs/research/analysis/validator-engine-disagreements-1.0.md', href);
    expect(ok(resolve('docs/research/analysis/validator-engine-disagreements-1.0.md', href)).url).toBe(
      '/spec/1.1.0/#appendix-c-changes-from-100',
    );
  });

  it('checks a same-page anchor against the file itself', () => {
    written('benchmarks/README.md', '#scenario-1-conflicting-sources');
    expect(ok(resolve('benchmarks/README.md', '#scenario-1-conflicting-sources'))).toEqual({
      kind: 'same-page',
      url: '#scenario-1-conflicting-sources',
      anchorChecked: true,
    });
  });

  it('gives an absolute Markdown-copy URL in md mode', () => {
    // Plan, recommended default 5: each page's copy is <route>index.md.
    expect(ok(resolve('spec/STANDARD-v1.1.0.md', 'RFC-0003-orchestration-extensions.md', 'md')).url).toBe(
      `${SITE_ORIGIN}/rfcs/0003/index.md`,
    );
  });
});

describe('links to files the site does not render', () => {
  it('sends YAML to GitHub', () => {
    written('skills/README.md', '../schemas/workflow_catalog.yaml');
    expect(ok(resolve('skills/README.md', '../schemas/workflow_catalog.yaml'))).toEqual({
      kind: 'github-file',
      url: blob('schemas/workflow_catalog.yaml'),
      anchorChecked: false,
    });
  });

  it('sends LICENSE to GitHub', () => {
    written('README.md', 'LICENSE');
    expect(ok(resolve('README.md', 'LICENSE')).url).toBe(blob('LICENSE'));
  });

  it('reads docs/schemas/ as schemas/, because git tracks only the symlink', () => {
    expect(TRACKED_FILES.has('docs/schemas')).toBe(true);
    expect(ok(resolve('docs/FAQ.md', 'schemas/capability_ontology.yaml')).url).toBe(blob('schemas/capability_ontology.yaml'));
  });

  it('sends a tracked but excluded .md file to GitHub and still checks its anchor', () => {
    // CLAUDE.md is tracked and on the plan's exclusion list (default 12).
    expect(TRACKED_FILES.has('CLAUDE.md')).toBe(true);
    expect(computeAnchors(readRepoFile('CLAUDE.md')).all.has('commands')).toBe(true);
    expect(ok(resolve('README.md', 'CLAUDE.md#commands'))).toEqual({
      kind: 'github-file',
      url: blob('CLAUDE.md#commands'),
      anchorChecked: true,
    });
    expect(resolve('README.md', 'CLAUDE.md#not-a-heading').ok).toBe(false);
  });
});

describe('links to directories', () => {
  it('maps a domain folder to its page', () => {
    written('README.md', 'docs/domains/healthcare/');
    expect(ok(resolve('README.md', 'docs/domains/healthcare/'))).toEqual({
      kind: 'directory-route',
      url: '/domains/healthcare/',
      anchorChecked: false,
    });
  });

  it('maps the ISO 42001 folder to its index page', () => {
    expect(ok(resolve('docs/compliance/eu-ai-act/README.md', '../iso42001/')).url).toBe('/compliance/iso-42001/');
  });

  it('sends an unmapped folder to its GitHub tree page', () => {
    written('docs/research/failure_taxonomy.md', './raw_data/');
    expect(ok(resolve('docs/research/failure_taxonomy.md', './raw_data/'))).toEqual({
      kind: 'github-tree',
      url: tree('docs/research/raw_data'),
      anchorChecked: false,
    });
  });
});

describe('links that must fail', () => {
  const reason = (r: Resolution) => (r.ok ? `resolved to ${r.url}` : r.reason);

  it('rejects a missing heading', () => {
    expect(reason(resolve('README.md', 'spec/STANDARD-v1.1.0.md#6-no-such-section'))).toMatch(/no heading or anchor/);
  });

  it('rejects a file git does not track', () => {
    // docs/MEDIUM_ARTICLE*.md are untracked drafts (plan, default 12).
    expect([...TRACKED_FILES].some((p) => p.startsWith('docs/MEDIUM_ARTICLE'))).toBe(false);
    expect(reason(resolve('docs/FAQ.md', 'MEDIUM_ARTICLE.md'))).toMatch(/not a file or directory tracked by git/);
  });

  it('rejects a path that leaves the repository', () => {
    expect(reason(resolve('README.md', '../outside.md'))).toBe('path leaves the repository');
  });

  it('rejects an anchor on a directory link', () => {
    expect(reason(resolve('README.md', 'docs/domains/#top'))).toMatch(/directory link cannot carry/);
  });

  it('leaves external links alone', () => {
    expect(ok(resolve('README.md', 'https://example.org/a.md'))).toEqual({
      kind: 'external',
      url: 'https://example.org/a.md',
      anchorChecked: false,
    });
    expect(ok(resolve('README.md', 'mailto:someone@example.org')).kind).toBe('external');
    expect(ok(resolve('README.md', 'http://example.org/')).kind).toBe('external');
    expect(ok(resolve('README.md', '//example.org/a')).kind).toBe('external');
  });

  it('rejects a scheme that can run script or is not a web link', () => {
    // GitHub drops these links, so a source that uses one looks harmless in
    // review while the site would make it live.
    for (const href of ['javascript:alert(1)', 'JavaScript:alert(1)', 'data:text/html,<script>alert(1)</script>', 'vbscript:msgbox(1)', 'file:///etc/passwd']) {
      expect(reason(resolve('README.md', href)), href).toMatch(/^unsafe link scheme/);
    }
  });

  it('rejects a link that is only a query string, naming the real problem', () => {
    expect(reason(resolve('README.md', '?tab=readme'))).toBe('a link with only a query string has no target');
    expect(reason(resolve('README.md', '?tab=readme#top'))).toMatch(/no heading or anchor "#top"/);
  });
});

describe('unsafe schemes through the real pipeline', () => {
  for (const [label, md] of [
    ['inline link', '[click](javascript:alert(1))'],
    ['image', '![x](data:image/svg+xml,<svg/onload=alert(1)>)'],
    ['link definition', '[click][j]\n\n[j]: javascript:alert(1)'],
  ] as const) {
    it(`fails the build on a javascript: or data: ${label}`, async () => {
      const text = `${readRepoFile('docs/FAQ.md')}\n\n${md}\n`;
      await expect(renderRepoFile('docs/FAQ.md', text)).rejects.toThrow(/unsafe link scheme/);
    });
  }
});

describe('resolver on a hand-made tree', () => {
  // Pure inputs, so no fixture file is tracked under site/ (it would need a
  // route of its own and validate_doc_links.py would scan it).
  const files: Record<string, string> = {
    'a/README.md': '# A\n\nSee [b](../b/doc.md#part-two).\n',
    'b/doc.md': '# Doc\n\n## Part one\n\n## Part two\n\n<a name="legacy"></a>\n',
    'b/data.yaml': 'x: 1\n',
  };
  const r = createResolver({
    tracked: new Set(Object.keys(files)),
    routeOf: (s) => ({ 'a/README.md': '/a/', 'b/doc.md': '/b/doc/' })[s],
    directories: { a: '/a/' },
    read: (p) => files[p]!,
    githubBase: 'https://github.com/o/r',
    site: 'https://example.org',
  });

  it('applies each rule', () => {
    expect(ok(r('a/README.md', '../b/doc.md#part-two')).url).toBe('/b/doc/#part-two');
    expect(ok(r('a/README.md', '../b/doc.md#legacy')).url).toBe('/b/doc/#legacy');
    expect(ok(r('a/README.md', '/b/data.yaml')).url).toBe('https://github.com/o/r/blob/main/b/data.yaml');
    expect(ok(r('b/doc.md', '../a/')).url).toBe('/a/');
    expect(ok(r('a/README.md', '../b/')).url).toBe('https://github.com/o/r/tree/main/b');
    expect(ok(r('a/README.md', '../b/doc%2Emd')).url).toBe('/b/doc/');
    expect(r('a/README.md', '../b/doc.md#part-three').ok).toBe(false);
    expect(r('a/README.md', '../b/doc.md/').ok).toBe(false);
  });
});

describe('anchors', () => {
  it('ignores SKILL.md frontmatter, which would otherwise parse as a heading', () => {
    // skills/detect/SKILL.md opens with a frontmatter block and has no H1; its
    // first heading is "## Intent".
    const text = readRepoFile('skills/detect/SKILL.md');
    expect(text.startsWith('---\n')).toBe(true);
    expect(anchorsOf('skills/detect/SKILL.md', readRepoFile).headings[0]).toBe('intent');
  });

  it('counts the frontmatter lines so errors name the source line', () => {
    const text = readRepoFile('skills/detect/SKILL.md');
    const closing = text.split('\n').indexOf('---', 1);
    // Astro trims the body, so the blank line after the frontmatter is skipped too.
    const firstBodyLine = text.split('\n').findIndex((l, i) => i > closing && l.trim() !== '');
    expect(bodyLineOffset(text)).toBe(firstBodyLine);
  });
});
