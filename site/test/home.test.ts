// Facts on the home page that come from the current Standard. Expected values
// are a line scan of the Standard file, not the page's own helpers.
import { describe, expect, it } from 'vitest';
import { coverage, faq, inlineText } from '../src/lib/home';
import { repoText, standardFileVersions } from './independent';

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
