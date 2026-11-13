// One file per profile of the data API (src/lib/api.ts, operation readProfile).
import type { APIRoute, GetStaticPaths } from 'astro';
import { endpointById, jsonResponse } from '../../../../lib/api';

const endpoint = endpointById('readProfile');

export const getStaticPaths = (() => endpoint.param!.values().map((value) => ({ params: { value } }))) satisfies GetStaticPaths;

export const GET: APIRoute = ({ params }) => jsonResponse(endpoint.payload(params.value));
