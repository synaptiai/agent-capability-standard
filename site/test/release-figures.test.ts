// The release notes figures (issue #125). Expected values are counted by hand
// from the fixture below, never taken from the functions under test.
import type { Root } from 'hast';
import remarkGfm from 'remark-gfm';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import { unified } from 'unified';
import { describe, expect, it } from 'vitest';
import { releaseBars } from '../src/lib/index-figures';
import { drawReleaseFigures } from '../src/plugins/release-figures-hast';
import {
  entryCodes,
  entryIssues,
  issueCounts,
  kindCount,
  kindsInUse,
  LONG_SECTION,
  parseReleases,
  releaseHeading,
  sectionCodes,
  sectionHasFigure,
} from '../src/lib/release-figures';

const FIXTURE = [
  '# Changelog',
  '',
  'Intro text.',
  '',
  '## [Unreleased]',
  '',
  '### Fixed',
  '- one fix (#7)',
  '',
  '## [v2.0.0] — 2026-10-29',
  '',
  'A paragraph that is not an entry.',
  '',
  '**Upgrading:**',
  '- an upgrade note, not under a kind heading',
  '',
  '### Added',
  ...Array.from({ length: 9 }, (_, i) => (i < 3 ? `- added ${i} (#114) raises W616` : i === 3 ? '- added 3 (#104, #114)\n  continues with R402 and X999' : `- added ${i}`)),
  '',
  '### Changed',
  '- changed 0',
  '',
  '## [v1.0.0] — 2026-01-24',
  '',
  '### Removed',
  '- removed 0',
  '- removed 1',
].join('\n');

describe('parseReleases', () => {
  const r = parseReleases(FIXTURE);
  it('reads every release heading, with its date', () => {
    expect(r.map((x) => [x.version, x.date])).toEqual([
      ['Unreleased', null],
      ['v2.0.0', '2026-10-29'],
      ['v1.0.0', '2026-01-24'],
    ]);
  });
  it('counts only top-level entries under a kind heading', () => {
    expect(kindCount(r[1]!, 'Added')).toBe(9);
    expect(kindCount(r[1]!, 'Changed')).toBe(1);
    expect(kindCount(r[1]!, 'Fixed')).toBe(0);
    expect(kindCount(r[2]!, 'Removed')).toBe(2);
  });
  it('keeps a continuation line with its entry', () => {
    expect(r[1]!.kinds[0]!.entries[3]!.text).toContain('continues with R402');
  });
  it('orders kinds as Keep a Changelog does', () => {
    expect(kindsInUse(r)).toEqual(['Added', 'Changed', 'Removed', 'Fixed']);
  });
});

describe('entry marks', () => {
  it('finds issues and codes', () => {
    expect(entryIssues('see (#104, #114) and #104 again; not &#38;')).toEqual(['104', '114']);
    expect(entryCodes('W616 then R402, W616 again, not W61 or AW6160')).toEqual(['W616', 'R402']);
  });
});

describe('long sections', () => {
  const added = parseReleases(FIXTURE)[1]!.kinds[0]!;
  it('counts issues by entries citing them, and entries citing none', () => {
    // Entries 0-2 cite #114, entry 3 cites #104 and #114; 4-8 cite none.
    expect(issueCounts(added)).toEqual({ rows: [{ issue: '114', count: 4 }, { issue: '104', count: 1 }], none: 5 });
  });
  it('keeps only codes the Standard defines', () => {
    expect(sectionCodes(added, new Set(['W616', 'R402']))).toEqual(['R402', 'W616']);
  });
  it('draws a figure only for a long section with marks', () => {
    expect(added.entries.length).toBeGreaterThanOrEqual(LONG_SECTION);
    expect(sectionHasFigure(added, new Set())).toBe(true);
    const plain = { kind: 'Added', entries: Array.from({ length: LONG_SECTION }, () => ({ text: 'x', issues: [], codes: [] })) };
    expect(sectionHasFigure(plain, new Set())).toBe(false);
  });
});

describe('release headings and bullets as Keep a Changelog writes them', () => {
  // Keep a Changelog 1.1.0 writes "## [1.1.0] - 2019-02-15" with "- " bullets;
  // CommonMark also allows "* " and "+ ".
  const text = ['# Changelog', '', '## [v3.0.0] - 2027-02-01', '', '### Added', '* star', '+ plus', '- dash', '', '## [v2.0.0] – 2027-01-01', '', '### Fixed', '- one', ''].join('\n');

  it('reads a hyphen or an en dash between version and date', () => {
    expect(parseReleases(text).map((r) => [r.version, r.date])).toEqual([
      ['v3.0.0', '2027-02-01'],
      ['v2.0.0', '2027-01-01'],
    ]);
    expect(releaseBars(text).rows.map((r) => [r.label, r.value])).toEqual([
      ['v3.0.0', 3],
      ['v2.0.0', 1],
    ]);
  });

  it('counts "* ", "+ " and "- " entries', () => {
    expect(parseReleases(text)[0]!.kinds[0]!.entries.map((e) => e.text)).toEqual(['star', 'plus', 'dash']);
  });

  it('throws on a "## [" heading in another form instead of dropping the section', () => {
    expect(() => releaseHeading('## [v3.0.0] 2027-02-01')).toThrow(/is not "## \[version\]"/);
    expect(() => parseReleases(text.replace('## [v2.0.0] – 2027-01-01', '## [v2.0.0] (2027-01-01)'))).toThrow(/v2\.0\.0\] \(2027/);
    expect(() => releaseBars(text.replace('## [v2.0.0] – 2027-01-01', '## [v2.0.0] (2027-01-01)'))).toThrow(/v2\.0\.0\] \(2027/);
  });
});

describe('the rendered entries of every kind section match the parser', () => {
  const draw = (md: string) => {
    const p = unified().use(remarkParse).use(remarkGfm).use(remarkRehype);
    const tree = p.runSync(p.parse(md)) as Root;
    drawReleaseFigures(tree, md, (b) => b);
    return tree;
  };

  it('passes when every section renders the entries the parser counts', () => {
    expect(() => draw(FIXTURE)).not.toThrow();
  });

  it('throws for a short section whose rendered list differs from the parsed entries', () => {
    // An ordered list renders one item the parser does not count as an entry.
    const md = ['## [v1.0.0] — 2026-01-24', '', '### Removed', '- removed 0', '', '1. numbered', ''].join('\n');
    expect(() => draw(md)).toThrow(/v1\.0\.0 Removed renders 2 entries, the parser found 1/);
  });

  it('finds a release whose heading a link definition renders as a link, and checks it', () => {
    // Keep a Changelog closes the file with "[v1.0.0]: https://…" link definitions.
    const md = ['## [v1.0.0] - 2026-01-24', '', '### Removed', '- removed 0', '', '1. numbered', '', '[v1.0.0]: https://example.com/v1.0.0', ''].join('\n');
    expect(() => draw(md)).toThrow(/v1\.0\.0 Removed renders 2 entries, the parser found 1/);
  });

  it('throws when a parsed release has no rendered heading', () => {
    const p = unified().use(remarkParse).use(remarkGfm).use(remarkRehype);
    const tree = p.runSync(p.parse('## Other\n\ntext\n')) as Root;
    expect(() => drawReleaseFigures(tree, '## [v1.0.0] - 2026-01-24\n\n### Fixed\n- a\n', (b) => b)).toThrow('CHANGELOG.md: no rendered heading for v1.0.0');
  });

  it('matches two sections of the same kind in one release by order', () => {
    const md = ['## [v1.0.0] — 2026-01-24', '', '### Fixed', '- a', '- b', '', '### Fixed', '- c', ''].join('\n');
    expect(() => draw(md)).not.toThrow();
  });
});

describe('fenced lines', () => {
  it('does not count a bullet inside a code fence as an entry', () => {
    // Hand count: 3 real entries; the 2 fenced "- " lines are code.
    const text = ['## [v1.0.0] — 2026-01-01', '', '### Added', '- one', '- two', '', '```yaml', '- not an entry', '- nor this', '```', '', '- three', ''].join('\n');
    expect(kindCount(parseReleases(text)[0]!, 'Added')).toBe(3);
  });
});
