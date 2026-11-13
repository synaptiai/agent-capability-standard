// One file per capabilitie of the data API (src/lib/api.ts, operation readCapability).
import type { APIRoute, GetStaticPaths } from 'astro';
import { endpointById, jsonResponse } from '../../../../lib/api';

const endpoint = endpointById('readCapability');

export const getStaticPaths = (() => endpoint.param!.values().map((value) => ({ params: { value } }))) satisfies GetStaticPaths;

export const GET: APIRoute = ({ params }) => jsonResponse(endpoint.payload(params.value));
