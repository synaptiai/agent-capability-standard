// The release notes figures (issue #125). Expected values are counted by hand
// from the fixture below, never taken from the functions under test.
import { describe, expect, it } from 'vitest';
import {
  entryCodes,
  entryIssues,
  issueCounts,
  kindCount,
  kindsInUse,
  LONG_SECTION,
  parseReleases,
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
