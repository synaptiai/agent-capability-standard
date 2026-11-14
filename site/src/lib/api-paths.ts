// The fixed paths of the data API and its description. No imports, so the
// Astro config (through redirects.ts) and the build scripts can load it.
export const API_VERSION = 'v1';
export const API_BASE = `/api/${API_VERSION}`;
export const OPENAPI_PATH = '/openapi.json';
export const API_CATALOG_PATH = '/.well-known/api-catalog';
/** The profile URI of RFC 9727, for the media type of the api-catalog. */
export const API_CATALOG_PROFILE = 'https://www.rfc-editor.org/info/rfc9727';
export const DEVELOPERS_URL = '/developers/';
