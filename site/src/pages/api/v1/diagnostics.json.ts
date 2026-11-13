// diagnostics.json of the data API (src/lib/api.ts, operation listDiagnostics).
import { endpointById, jsonResponse } from '../../../lib/api';

export function GET(): Response {
  return jsonResponse(endpointById('listDiagnostics').payload());
}
