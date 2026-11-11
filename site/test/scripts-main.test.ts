// The check scripts must run their check however they are started. Node gives
// import.meta.url as the real path of the script but keeps a symlinked path in
// process.argv[1], so a script started through a symlink must still see that
// it is the main module, report its problems and exit 1.
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';

const scripts = path.resolve('scripts');
const tmp = mkdtempSync(path.join(tmpdir(), 'acs-scripts-'));
afterAll(() => rmSync(tmp, { recursive: true, force: true }));

function viaSymlink(script: string, args: string[]): { status: number | null; output: string } {
  const link = path.join(tmp, `link-${script}`);
  symlinkSync(path.join(scripts, script), link);
  const r = spawnSync(process.execPath, [link, ...args], { encoding: 'utf8' });
  return { status: r.status, output: `${r.stdout}${r.stderr}` };
}

describe('check scripts started through a symlink', () => {
  it('check-dist reports an empty dist and exits 1', () => {
    const dist = mkdtempSync(path.join(tmp, 'dist-'));
    const r = viaSymlink('check-dist.mjs', [dist]);
    expect(r.output).toMatch(/check-dist: \d+ problem\(s\)/);
    expect(r.status).toBe(1);
  });

  it('check-contrast reports a failing pair and exits 1', () => {
    const css = path.join(tmp, 'tokens.css');
    writeFileSync(css, ':root { --bg: #ffffff; --text: #ffffff; }\n');
    const r = viaSymlink('check-contrast.mjs', [css]);
    expect(r.output).toMatch(/check-contrast: /);
    expect(r.status).toBe(1);
  });

  it('check-design-data runs its checks', () => {
    const r = viaSymlink('check-design-data.mjs', []);
    expect(r.output).toMatch(/check-design-data: /);
  });
});
