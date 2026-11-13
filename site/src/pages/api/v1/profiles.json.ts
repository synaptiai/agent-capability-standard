// profiles.json of the data API (src/lib/api.ts, operation listProfiles).
import { endpointById, jsonResponse } from '../../../lib/api';

export function GET(): Response {
  return jsonResponse(endpointById('listProfiles').payload());
}
