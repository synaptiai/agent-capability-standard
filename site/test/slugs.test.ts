// Every Markdown source in the route table, rendered through the build's own
// pipeline, must give each heading the id GitHub gives it. The expected ids are
// computed straight from the source with github-slugger (one slugger per file,
// headings in document order, frontmatter removed), the way GitHub and the
// spike's check-slugs script do, not with src/lib/anchors.ts. This covers
// the sources shown inside generated pages too, which `dist/` does not have yet.
import { beforeAll, describe, expect, it } from 'vitest';
import { computeAnchors } from '../src/lib/anchors';
import { compareIds, githubHeadingIds, renderedHeadingIds } from '../src/lib/check-slugs';
import { readRepoFile, TRACKED_FILES } from '../src/lib/repo';
import { publicMarkdown, ROUTES } from '../src/lib/routes';
import { renderRepoFile } from './pipeline';

const sources = ROUTES.flatMap((r) => (r.source === null ? [] : [r.source]));

// The two comparisons below parse every source's Markdown again (about 170
// files, many with long tables and diagram fences), which takes several
// seconds and failed vitest's 5-second default at 045c0cc already. The work
// grows with the documentation, not with a fault, so they get a fixed budget.
const PARSE_ALL_TIMEOUT = 60_000;

const rendered = new Map<string, string>();
const failures: string[] = [];

beforeAll(async () => {
  for (const s of sources) {
    try {
      rendered.set(s, (await renderRepoFile(s)).code);
    } catch (e) {
      failures.push(`${s}: ${(e as Error).message}`);
    }
  }
}, 300_000);

describe('every Markdown source through the build pipeline', () => {
  it('covers every public Markdown file, once each', () => {
    // The public set: git ls-files, .md, minus the plan's exclusions.
    expect(sources.length).toBe(new Set(sources).size);
    expect([...sources].sort()).toEqual(publicMarkdown(TRACKED_FILES));
  });

  it('renders without a link, HTML or metadata error', () => {
    expect(failures).toEqual([]);
  });

  it('gives every heading the id GitHub gives it', () => {
    const mismatches: string[] = [];
    let compared = 0;
    for (const s of sources) {
      const html = rendered.get(s);
      if (html === undefined) continue;
      const want = githubHeadingIds(readRepoFile(s));
      compared += want.length;
      const diff = compareIds(want, renderedHeadingIds(html));
      if (diff) mismatches.push(`${s}: ${diff}`);
    }
    expect(mismatches).toEqual([]);
    expect(compared).toBeGreaterThan(1000);
  }, PARSE_ALL_TIMEOUT);

  it('gives the link resolver the same heading anchors the pages render', () => {
    // src/lib/anchors.ts decides which #fragments a link may use; it must
    // agree with what is rendered, or a checked anchor could still be dead.
    const mismatches: string[] = [];
    for (const s of sources) {
      const html = rendered.get(s);
      if (html === undefined) continue;
      const diff = compareIds(computeAnchors(readRepoFile(s)).headings, renderedHeadingIds(html));
      if (diff) mismatches.push(`${s}: ${diff}`);
    }
    expect(mismatches).toEqual([]);
  }, PARSE_ALL_TIMEOUT);

  it('keeps the spec ids people already link to', () => {
    const spec = rendered.get('spec/STANDARD-v1.1.0.md') ?? '';
    // Plan, recommended default 4, and the spike's done-check.
    for (const id of ['521-safety-flags', '5-workflow-dsl', 'appendix-c-changes-from-100']) {
      expect(spec).toContain(`id="${id}"`);
    }
  });
});
