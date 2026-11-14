// workflows.json of the data API (src/lib/api.ts, operation listWorkflows).
import { endpointById, jsonResponse } from '../../../lib/api';

export function GET(): Response {
  return jsonResponse(endpointById('listWorkflows').payload());
}
