// pages.json of the data API (src/lib/api-pages.ts, operation listPages).
import { jsonResponse } from '../../../lib/api';
import { pagesFile } from '../../../lib/api-pages';

export async function GET(): Promise<Response> {
  return jsonResponse(await pagesFile());
}
