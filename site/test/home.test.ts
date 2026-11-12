// Facts on the home page that come from the current Standard. Expected values
// are a line scan of the Standard file, not the page's own helpers.
import { describe, expect, it } from 'vitest';
import { coverage, faq, gallery, galleryCaption, getStarted, inlineText, principles, tableCaption } from '../src/lib/home';
import { resolveGlyphKey } from '../src/pixel/keys';
import { allCatalogSteps, claudeLayerTable, repoText, standardFileVersions } from './independent';

const standard = () => repoText(`spec/STANDARD-v${standardFileVersions()[0]!}.md`);

describe('home page facts from the Standard', () => {
  it('names the section that defines the diagnostic codes in the Validator card', () => {
    const num = /^## (\d+)\. Diagnostic/m.exec(standard())![1]!;
    const validator = coverage().tools.find((c) => c.title === 'Validator')!;
    expect(validator.line).toContain(`diagnostic codes of section ${num}.`);
  });

  it('states the minimum deprecation period of the deprecation policy', () => {
    const text = standard();
    const policy = text.slice(text.indexOf('### 11.2 Deprecation Policy'), text.indexOf('### 11.3'));
    const months = /Minimum deprecation period: (\d+) months/.exec(policy)![1]!;
    const answer = faq().items.find((i) => i.question === 'How stable is it?')!;
    expect(inlineText(answer.answer)).toContain(`at least ${months} months later`);
  });
});

describe('home page figures (visual spec 3.11)', () => {
  it('draws one gallery row per catalog workflow, in file order, with its step count', () => {
    const scan = allCatalogSteps();
    const rows = gallery().flatMap((g) => g.items.map((i) => [i.workflow.id, i.steps] as const));
    expect(rows).toEqual([...scan].map(([id, caps]) => [id, caps.length]));
  });

  it('states the workflow count and the step range in the gallery caption', () => {
    const lengths = [...allCatalogSteps().values()].map((c) => c.length);
    expect(galleryCaption()).toMatch(new RegExp(`^${lengths.length} workflows in \\d+ groups, from ${Math.min(...lengths)} to ${Math.max(...lengths)} steps;`));
  });

  it('gives the periodic table caption the smallest and largest layer of the CLAUDE.md layer table', () => {
    const rows = claudeLayerTable();
    const total = rows.reduce((n, r) => n + r.count, 0);
    const min = Math.min(...rows.map((r) => r.count));
    const max = Math.max(...rows.map((r) => r.count));
    const caption = tableCaption();
    expect(caption.startsWith(`${total} capabilities in ${rows.length} layers, from ${min} in `)).toBe(true);
    for (const r of rows.filter((x) => x.count === min || x.count === max)) expect(caption).toContain(r.id);
  });

  it('puts the CLAUDE.md capability and layer counts on the reference-data cards', () => {
    const rows = claudeLayerTable();
    const data = coverage().data;
    expect(data.find((c) => c.title === 'Capabilities')!.count).toBe(rows.reduce((n, r) => n + r.count, 0));
    expect(data.find((c) => c.title === 'Layers')!.count).toBe(rows.length);
    expect(data.find((c) => c.title === 'Workflows')!.count).toBe(allCatalogSteps().size);
  });

  it('gives every principle of section 3 and every coverage and get-started card a drawn glyph', () => {
    const h3 = [...standard().split('## 3. ')[1]!.split('\n## ')[0]!.matchAll(/^### 3\.\d+ (.+)$/gm)].map((m) => m[1]!);
    expect(principles().items.map((p) => p.title)).toEqual(h3);
    const cov = coverage();
    const keys = [...principles().items, ...cov.standard, ...cov.data, ...cov.tools, ...getStarted().cards].map((x) => x.glyph);
    for (const k of keys) expect(k && resolveGlyphKey(k), String(k)).toBeTruthy();
  });
});
