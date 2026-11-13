// parseLogDates on a hand-written `git log --format=%x00%cI --name-only`
// output, and the front matter of a copy on hand-written values.
import { describe, expect, it } from 'vitest';
import { parse } from 'yaml';
import { frontmatter } from '../src/lib/copy-frontmatter';
import { parseLogDates } from '../src/lib/page-dates';
import type { Route } from '../src/lib/routes';

describe('parseLogDates', () => {
  it('keeps the newest date of each path; commits come newest first', () => {
    const log = '\u00002026-11-12T10:00:00+01:00\n\na.md\nb.md\n\u00002026-11-01T09:00:00+01:00\n\nb.md\nc.md\n';
    expect(Object.fromEntries(parseLogDates(log))).toEqual({
      'a.md': '2026-11-12T10:00:00+01:00',
      'b.md': '2026-11-12T10:00:00+01:00',
      'c.md': '2026-11-01T09:00:00+01:00',
    });
  });

  it('skips a commit that touched no file (a merge)', () => {
    expect(parseLogDates('\u00002026-11-12T10:00:00+01:00\n\n\u00002026-11-11T10:00:00+01:00\n\nx.md\n').get('x.md')).toBe('2026-11-11T10:00:00+01:00');
  });
});

describe('frontmatter', () => {
  const route = { url: '/a/b/', source: 'x.md', section: 'guides', order: 0, template: 'prose', title: 'T' } as Route;

  it('writes values YAML reads back unchanged, colons and quotes included', () => {
    const fm = frontmatter(route, { title: 'Edge types: "requires" and more', description: 'One\nline: two' }, '2026-11-12T10:00:00+01:00');
    expect(fm.startsWith('---\n')).toBe(true);
    expect(fm.endsWith('\n---\n\n')).toBe(true);
    expect(parse(fm.slice(4, -6))).toEqual({
      title: 'Edge types: "requires" and more',
      description: 'One line: two',
      canonical: 'https://acs.synapti.ai/a/b/',
      last_updated: '2026-11-12T10:00:00+01:00',
    });
  });

  it('leaves out a missing description or date', () => {
    expect(frontmatter(route, { title: 'T', description: null }, null)).toBe('---\ntitle: "T"\ncanonical: "https://acs.synapti.ai/a/b/"\n---\n\n');
  });
});

describe('pageSources', () => {
  it('fails on a source file that does not exist', async () => {
    const { pageSources } = await import('../src/lib/page-dates');
    const route = { source: 'docs/NO_SUCH_FILE.md', url: '/nowhere/', section: 'guides', template: 'prose' } as unknown as Route;
    expect(() => pageSources(route)).toThrow(/page-dates: \/nowhere\/ names docs\/NO_SUCH_FILE\.md, which does not exist/);
  });
});
