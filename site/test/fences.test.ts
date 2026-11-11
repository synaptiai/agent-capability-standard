// Code fence languages. Every language a routed source uses must be one Shiki
// ships, one of its plain-text names, or aliased in SHIKI_CONFIG. Languages are
// read from parsed `code` nodes, not with a regex, because fences nest.
// The ebnf case: spec/STANDARD-v1.1.0.md opens an ebnf fence (line 450 at
// 9945a39), Shiki 4.6.0 has no EBNF grammar (design notes, "pipeline" section 0), and the alias must
// make it render as plain text without Shiki's "doesn't exist" warning.
import type { Code } from 'mdast';
import { bundledLanguages, isSpecialLang } from 'shiki';
import { visit } from 'unist-util-visit';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { parseMarkdown } from '../src/lib/anchors';
import { SHIKI_CONFIG } from '../src/lib/markdown';
import { readRepoFile } from '../src/lib/repo';
import { markdownSources } from '../src/lib/routes';
import { renderRepoFile } from './pipeline';

function fenceLanguages(): Map<string, string[]> {
  const langs = new Map<string, string[]>();
  for (const s of markdownSources()) {
    visit(parseMarkdown(readRepoFile(s)), 'code', (node: Code) => {
      if (!node.lang) return;
      const where = langs.get(node.lang) ?? [];
      where.push(`${s}:${node.position?.start.line ?? '?'}`);
      langs.set(node.lang, where);
    });
  }
  return langs;
}

afterEach(() => vi.restoreAllMocks());

describe('code fence languages', () => {
  const langs = fenceLanguages();
  const alias = SHIKI_CONFIG.langAlias ?? {};

  it('finds the languages the design counted', () => {
    // Design notes, "pipeline" section 0: yaml, console, bash, python, json,
    // text, markdown, xml, ebnf and bibtex appear in the public Markdown.
    for (const l of ['yaml', 'console', 'bash', 'python', 'json', 'text', 'markdown', 'xml', 'ebnf', 'bibtex']) {
      expect(langs.has(l), l).toBe(true);
    }
  });

  it('knows every language in the sources', () => {
    const unknown = [...langs.keys()].filter((l) => !(l in bundledLanguages) && !isSpecialLang(l) && !(l in alias));
    expect(unknown).toEqual([]);
  });

  it('aliases only languages Shiki lacks', () => {
    for (const from of Object.keys(alias)) expect(from in bundledLanguages, from).toBe(false);
  });

  it('finds the ebnf fence of spec/STANDARD-v1.1.0.md where a line scan does', () => {
    // A plain line scan for an opening ```ebnf, not the Markdown parser above.
    const scanned = markdownSources().flatMap((s) =>
      readRepoFile(s)
        .split('\n')
        .flatMap((l, i) => (/^```ebnf\s*$/.test(l) ? [`${s}:${i + 1}`] : [])),
    );
    expect(scanned.some((w) => w.startsWith('spec/STANDARD-v1.1.0.md:'))).toBe(true);
    expect(langs.get('ebnf')).toEqual(scanned);
  });
});

describe('Shiki in the build pipeline', () => {
  it('renders ebnf as plain text with no warning, using the CSS-variable theme', async () => {
    const warn = vi.spyOn(console, 'warn');
    const { code } = await renderRepoFile('spec/STANDARD-v1.1.0.md');
    expect(warn.mock.calls.filter((c) => String(c[0]).includes('[Shiki]'))).toEqual([]);
    const ebnf = /<pre class="astro-code css-variables"[^>]*data-language="ebnf">/.exec(code);
    expect(ebnf).not.toBeNull();
    expect(ebnf![0]).toContain('background-color:var(--astro-code-background)');
    // yaml blocks get token colours from the theme's variables.
    expect(code).toMatch(/data-language="yaml"/);
    expect(code).toContain('var(--astro-code-token-keyword)');
  });

  it('warns for a language that is neither shipped nor aliased', async () => {
    // Control for the test above: without an alias, Shiki says so.
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const text = `${readRepoFile('docs/FAQ.md')}\n\n\`\`\`no-such-language-xyz\nx\n\`\`\`\n`;
    await renderRepoFile('docs/FAQ.md', text);
    expect(warn.mock.calls.some((c) => String(c[0]).includes('"no-such-language-xyz" doesn\'t exist'))).toBe(true);
  });
});
