// /.well-known/api-catalog (RFC 9727): a linkset that points at the data
// API's OpenAPI document and its documentation. public/_headers serves it as
// application/linkset+json with the profile of RFC 9727.
import { apiCatalog, jsonText } from '../../lib/api';

export function GET(): Response {
  return new Response(jsonText(apiCatalog()), { headers: { 'Content-Type': 'application/linkset+json' } });
}
