// Whether the module at `metaUrl` (its import.meta.url) is the script node was
// started with. Node gives import.meta.url as the real path but keeps a
// symlinked path in process.argv[1], so both are compared as real paths.
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export function isMain(metaUrl) {
  const arg = process.argv[1];
  if (!arg) return false;
  try {
    return realpathSync(arg) === realpathSync(fileURLToPath(metaUrl));
  } catch {
    return false;
  }
}
