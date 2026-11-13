// edges.json of the data API (src/lib/api.ts, operation listEdges).
import { endpointById, jsonResponse } from '../../../lib/api';

export function GET(): Response {
  return jsonResponse(endpointById('listEdges').payload());
}
