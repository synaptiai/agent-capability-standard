// One file per workflow of the data API (src/lib/api.ts, operation readWorkflow).
import type { APIRoute, GetStaticPaths } from 'astro';
import { endpointById, jsonResponse } from '../../../../lib/api';

const endpoint = endpointById('readWorkflow');

export const getStaticPaths = (() => endpoint.param!.values().map((value) => ({ params: { value } }))) satisfies GetStaticPaths;

export const GET: APIRoute = ({ params }) => jsonResponse(endpoint.payload(params.value));
