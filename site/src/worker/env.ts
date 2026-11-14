// What the worker is given: the Pages ASSETS binding and the facts the build
// fills in. Kept free of @cloudflare/workers-types; the worker only uses the
// web-standard Request and Response.

/** The Pages binding that serves the deployed static files. */
export interface Assets {
  fetch(input: Request | string | URL, init?: RequestInit): Promise<Response>;
}

export interface Env {
  ASSETS: Assets;
}

/** Facts read from the repository when the site is built (src/lib/worker-build.ts). */
export interface WorkerConfig {
  /** The release of this repository (.claude-plugin/plugin.json), the MCP server's version. */
  version: string;
  /** The current version of the Standard, e.g. "1.1.0". */
  standardVersion: string;
  /** Production origin, used for canonical links and absolute URLs. */
  origin: string;
  /** The 302 redirects of public/_redirects, from path to target (src/lib/redirects.ts). */
  redirects: Readonly<Record<string, string>>;
}
