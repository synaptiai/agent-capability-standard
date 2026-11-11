// The social image every page points to, drawn from the mark.
import { ogPng } from '../pixel/icons';

export function GET(): Response {
  return new Response(new Uint8Array(ogPng()), { headers: { 'Content-Type': 'image/png' } });
}
