// Build the reference core's WebAssembly interface (core/src/wasm.rs) and
// copy it to dist/acs_core.wasm. The toolchain is rustup's choice, so
// RUSTUP_TOOLCHAIN selects it: CI sets it to the pinned toolchain it
// installed with the wasm32-unknown-unknown target.
import { execFileSync } from 'node:child_process';
import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const pkg = join(here, '..');
const core = join(pkg, '..', '..', 'core');
const TARGET = 'wasm32-unknown-unknown';

const run = (cmd, args) => execFileSync(cmd, args, { encoding: 'utf8', env: process.env, cwd: core });

const rustc = run('rustc', ['--version']).trim();
const toolchain = process.env.RUSTUP_TOOLCHAIN ?? '(rustup default)';
console.log(`toolchain ${toolchain}: ${rustc}`);
const installed = run('rustup', ['target', 'list', '--installed']).split('\n').map((t) => t.trim());
if (!installed.includes(TARGET)) {
  console.error(
    `the ${TARGET} target is not installed for ${toolchain}: ` +
      `rustup target add ${TARGET} --toolchain ${process.env.RUSTUP_TOOLCHAIN ?? '<toolchain>'}`,
  );
  process.exit(1);
}
execFileSync(
  'cargo',
  ['build', '--release', '--locked', '--target', TARGET, '--features', 'wasm', '--lib', '--manifest-path', join(core, 'Cargo.toml')],
  { stdio: 'inherit', env: process.env, cwd: core },
);
mkdirSync(join(pkg, 'dist'), { recursive: true });
copyFileSync(join(core, 'target', TARGET, 'release', 'acs_core.wasm'), join(pkg, 'dist', 'acs_core.wasm'));
console.log('dist/acs_core.wasm');
