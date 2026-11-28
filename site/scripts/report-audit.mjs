// Reports the npm advisories against the site's lockfile, for the Site
// workflow. It runs `npm audit --package-lock-only --json` and prints one
// GitHub warning annotation that names every vulnerable package, and a
// table of the advisories for the run summary when GITHUB_STEP_SUMMARY is set.
// It always exits 0: an advisory published upstream must not stop the build
// or the deploy of main. An audit that cannot run (no registry, unreadable
// output) is reported as a warning too.
//
// Run: node scripts/report-audit.mjs [npm audit arguments]
// (extra arguments go to npm audit, for example --registry <url>).
import { spawnSync } from 'node:child_process';
import { appendFileSync } from 'node:fs';
import { isMain } from './is-main.mjs';

const SEVERITIES = ['critical', 'high', 'moderate', 'low', 'info'];

// Escapes text for the message of a workflow command, so that third-party
// text (advisory titles) cannot end the annotation or start another command.
export function escapeData(text) {
  return String(text).replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
}

// The advisories of an `npm audit --json` report (lockfile version 2 or 3
// format), one row per advisory and package, sorted by severity then name.
export function advisories(report) {
  const rows = [];
  for (const [name, vuln] of Object.entries(report?.vulnerabilities ?? {})) {
    for (const via of vuln.via ?? []) {
      if (typeof via !== 'object' || via === null) continue;
      const id = String(via.url ?? '').split('/').pop() || String(via.source ?? '');
      rows.push({
        name,
        severity: String(via.severity ?? vuln.severity ?? 'unknown'),
        id,
        title: String(via.title ?? ''),
        range: String(via.range ?? vuln.range ?? ''),
        url: String(via.url ?? ''),
      });
    }
  }
  const rank = (s) => {
    const i = SEVERITIES.indexOf(s);
    return i === -1 ? SEVERITIES.length : i;
  };
  return rows.sort((a, b) => rank(a.severity) - rank(b.severity) || a.name.localeCompare(b.name));
}

// The annotation line and the summary text for the result of one npm audit
// run: its exit status and its standard output.
export function report(status, stdout) {
  let parsed;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    parsed = null;
  }
  if (parsed === null || typeof parsed !== 'object' || parsed.error) {
    const why =
      parsed?.error?.summary || parsed?.message || `npm audit exited ${status} without a readable report`;
    return {
      annotation: `::warning file=site/package-lock.json,title=npm audit did not run::${escapeData(why)}`,
      summary: `### npm audit\n\nThe audit did not run: ${why}\n`,
    };
  }
  const rows = advisories(parsed);
  if (rows.length === 0) {
    return { annotation: null, summary: '### npm audit\n\nNo advisories against `site/package-lock.json`.\n' };
  }
  const names = [...new Set(rows.map((r) => `${r.name} (${r.severity}, ${r.id})`))].join('; ');
  const cell = (t) => t.replaceAll('|', '\\|').replace(/\s+/g, ' ');
  const table = rows.map(
    (r) => `| ${cell(r.name)} | ${cell(r.severity)} | [${cell(r.id)}](${r.url}) | ${cell(r.range)} | ${cell(r.title)} |`,
  );
  return {
    annotation:
      `::warning file=site/package-lock.json,title=npm audit found ${rows.length} advisor${rows.length === 1 ? 'y' : 'ies'}::` +
      escapeData(`${names}. Run npm audit in site/ for the fix.`),
    summary: [
      '### npm audit',
      '',
      `${rows.length} advisor${rows.length === 1 ? 'y' : 'ies'} against \`site/package-lock.json\`:`,
      '',
      '| Package | Severity | Advisory | Affected range | Title |',
      '| --- | --- | --- | --- | --- |',
      ...table,
      '',
    ].join('\n'),
  };
}

if (isMain(import.meta.url)) {
  const r = spawnSync('npm', ['audit', '--package-lock-only', '--json', ...process.argv.slice(2)], {
    encoding: 'utf8',
  });
  const { annotation, summary } = report(r.status, r.stdout ?? '');
  // Only the annotation line reaches standard output, so no line of npm's own
  // output can be read as a workflow command.
  if (annotation) console.log(annotation);
  else console.log('report-audit: no advisories');
  if (process.env.GITHUB_STEP_SUMMARY) {
    try {
      appendFileSync(process.env.GITHUB_STEP_SUMMARY, summary);
    } catch (e) {
      console.log(`::warning title=npm audit::${escapeData(`could not write the run summary: ${e}`)}`);
    }
  }
  process.exit(0);
}
