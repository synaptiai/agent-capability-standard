// capabilities.json of the data API (src/lib/api.ts, operation listCapabilities).
import { endpointById, jsonResponse } from '../../../lib/api';

export function GET(): Response {
  return jsonResponse(endpointById('listCapabilities').payload());
}
