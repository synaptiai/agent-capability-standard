// layers.json of the data API (src/lib/api.ts, operation listLayers).
import { endpointById, jsonResponse } from '../../../lib/api';

export function GET(): Response {
  return jsonResponse(endpointById('listLayers').payload());
}
