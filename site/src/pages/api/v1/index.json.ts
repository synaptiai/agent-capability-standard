// index.json of the data API (src/lib/api.ts, operation readApiIndex).
import { endpointById, jsonResponse } from '../../../lib/api';

export function GET(): Response {
  return jsonResponse(endpointById('readApiIndex').payload());
}
