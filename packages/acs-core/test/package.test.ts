// What the published package holds: `npm pack --dry-run` lists the built
// entries, the module, the bundled documents and the legal files, and no
// sources or tests; LICENSE and NOTICE are the repository's.
import { describe, expect, it } from 'vitest';

const CHILD = 'node:child_process';
const FS = 'node:fs/promises';

describe('the npm package', () => {
  it('packs dist, README, LICENSE and NOTICE only', async () => {
    const { execFileSync } = (await import(/* @vite-ignore */ CHILD)) as {
      execFileSync(cmd: string, args: string[], o: { cwd: URL; encoding: 'utf8' }): string;
    };
    const out = execFileSync('npm', ['pack', '--dry-run', '--json', '--ignore-scripts'], {
      cwd: new URL('..', import.meta.url),
      encoding: 'utf8',
    });
    const files = (JSON.parse(out) as { files: { path: string }[] }[])[0]?.files.map((f) => f.path) ?? [];
    for (const f of ['dist/index.js', 'dist/wasm.js', 'dist/acs_core.wasm', 'dist/documents.json', 'README.md', 'LICENSE', 'NOTICE']) {
      expect(files, f).toContain(f);
    }
    expect(files.filter((f) => f.startsWith('src/') || f.startsWith('test/'))).toEqual([]);
  });

  it('carries the repository LICENSE and NOTICE', async () => {
    const fs = (await import(/* @vite-ignore */ FS)) as { readFile(u: URL, e: 'utf8'): Promise<string> };
    for (const name of ['LICENSE', 'NOTICE']) {
      expect(await fs.readFile(new URL(`../${name}`, import.meta.url), 'utf8')).toBe(
        await fs.readFile(new URL(`../../../${name}`, import.meta.url), 'utf8'),
      );
    }
  });
});
