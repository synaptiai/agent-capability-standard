// The favicon as SVG, drawn from the mark, with its own dark-mode colours.
import { faviconSvg } from '../pixel/icons';

export function GET(): Response {
  return new Response(faviconSvg(), { headers: { 'Content-Type': 'image/svg+xml' } });
}
