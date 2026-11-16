import { describe, expect, it } from 'vitest';
import evalFixtures from '../../../tests/conformance/expressions/eval.json' with { type: 'json' };
import checkFixtures from '../../../tests/conformance/expressions/check.json' with { type: 'json' };
import { loadCore } from './core.js';

describe('the expression fixtures through the core', () => {
  it('evaluates every eval.json case', async () => {
    const core = await loadCore();
    for (const c of evalFixtures.cases) {
      const got = core.call('expr.eval', { expr: c.expr, bindings: c.bindings ?? {} });
      expect(got, c.id).toEqual(c.expect);
    }
  });

  it('checks every check.json case', async () => {
    const core = await loadCore();
    for (const c of checkFixtures.cases) {
      const got = core.call<{ codes: string[] }>('expr.check', { expr: c.expr, scope: checkFixtures.scope });
      expect(got.codes, c.id).toEqual(c.expect);
    }
  });
});
