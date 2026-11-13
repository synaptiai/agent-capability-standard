// /openapi.json: the OpenAPI 3.1 description of the data API (src/lib/openapi.ts).
import { jsonResponse } from '../lib/api';
import { openApiDocument } from '../lib/openapi';

export function GET(): Response {
  return jsonResponse(openApiDocument());
}
