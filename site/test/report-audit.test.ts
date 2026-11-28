// scripts/report-audit.mjs turns an `npm audit --json` report into one
// warning annotation and a run-summary table, and never fails the step.
// The reports below are hand-written in npm's format; the advisory is the
// one npm reported against astro 7.4.5.
import { describe, expect, it } from 'vitest';
import { advisories, escapeData, report } from '../scripts/report-audit.mjs';

const astro = {
  auditReportVersion: 2,
  vulnerabilities: {
    astro: {
      name: 'astro',
      severity: 'moderate',
      range: '5.14.3 - 7.4.6',
      via: [
        {
          source: 1119123,
          name: 'astro',
          title: 'Image endpoint | case-variant sibling\nof the output directory',
          url: 'https://github.com/advisories/GHSA-r3h5-4585-7x3w',
          severity: 'moderate',
          range: '>=5.14.3 <=7.4.6',
        },
      ],
    },
    // A package vulnerable only through another names it as a string.
    'astro-dep': { name: 'astro-dep', severity: 'high', range: '*', via: ['astro'] },
  },
};

describe('report-audit', () => {
  it('escapes the characters that would end or split a workflow command', () => {
    expect(escapeData('50%\r\n::error::x')).toBe('50%25%0D%0A::error::x');
  });

  it('lists each advisory once, from the vulnerability that carries it', () => {
    expect(advisories(astro)).toEqual([
      {
        name: 'astro',
        severity: 'moderate',
        id: 'GHSA-r3h5-4585-7x3w',
        title: 'Image endpoint | case-variant sibling\nof the output directory',
        range: '>=5.14.3 <=7.4.6',
        url: 'https://github.com/advisories/GHSA-r3h5-4585-7x3w',
      },
    ]);
  });

  it('warns with one annotation line and tabulates the advisories', () => {
    const { annotation, summary } = report(1, JSON.stringify(astro));
    expect(annotation).toBe(
      '::warning file=site/package-lock.json,title=npm audit found 1 advisory::' +
        'astro (moderate, GHSA-r3h5-4585-7x3w). Run npm audit in site/ for the fix.',
    );
    expect(annotation).not.toMatch(/[\r\n]/);
    expect(summary).toContain(
      '| astro | moderate | [GHSA-r3h5-4585-7x3w](https://github.com/advisories/GHSA-r3h5-4585-7x3w) | ' +
        '>=5.14.3 <=7.4.6 | Image endpoint \\| case-variant sibling of the output directory |',
    );
  });

  it('prints no annotation when there is no advisory', () => {
    const { annotation, summary } = report(0, JSON.stringify({ auditReportVersion: 2, vulnerabilities: {} }));
    expect(annotation).toBeNull();
    expect(summary).toContain('No advisories');
  });

  it('warns when the audit could not run', () => {
    const offline = JSON.stringify({
      message: 'request to http://127.0.0.1:9/ failed, reason: connect ECONNREFUSED',
      error: { summary: '', detail: '' },
    });
    expect(report(1, offline).annotation).toBe(
      '::warning file=site/package-lock.json,title=npm audit did not run::' +
        'request to http://127.0.0.1:9/ failed, reason: connect ECONNREFUSED',
    );
    expect(report(null, '').annotation).toBe(
      '::warning file=site/package-lock.json,title=npm audit did not run::' +
        'npm audit exited null without a readable report',
    );
  });
});
