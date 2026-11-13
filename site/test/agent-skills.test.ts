// skillFrontmatter on hand-written SKILL.md texts: a broken file is named in the error.
import { describe, expect, it } from 'vitest';
import { skillFrontmatter } from '../src/lib/agent-skills';

describe('skillFrontmatter', () => {
  it('reads the name and description', () => {
    expect(skillFrontmatter('---\nname: x\ndescription: " y "\n---\n# X\n', 'skills/x/SKILL.md')).toEqual({ name: 'x', description: 'y' });
  });
  it('names the file when the front matter is empty', () => {
    expect(() => skillFrontmatter('---\n\n---\n# X\n', 'skills/x/SKILL.md')).toThrow(/skills\/x\/SKILL\.md front matter is empty/);
  });
  it('names the file when the front matter is not valid YAML', () => {
    expect(() => skillFrontmatter('---\nname: [x\n---\n# X\n', 'skills/x/SKILL.md')).toThrow(/skills\/x\/SKILL\.md front matter is not valid YAML/);
  });
});
