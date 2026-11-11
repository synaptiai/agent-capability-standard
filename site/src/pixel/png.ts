// A small RGB raster and PNG encoder for the favicon and the social image,
// built from the grids at build time (no drawn image files in the repo).
import { crc32, deflateSync } from 'node:zlib';

export type Rgb = readonly [number, number, number];

export class Raster {
  readonly data: Uint8Array;

  constructor(
    readonly width: number,
    readonly height: number,
    background: Rgb,
  ) {
    this.data = new Uint8Array(width * height * 3);
    this.fill(0, 0, width, height, background);
  }

  /** Paint a rectangle, clipped to the raster. */
  fill(x: number, y: number, w: number, h: number, colour: Rgb): void {
    const x0 = Math.max(0, Math.round(x));
    const y0 = Math.max(0, Math.round(y));
    const x1 = Math.min(this.width, Math.round(x + w));
    const y1 = Math.min(this.height, Math.round(y + h));
    for (let yy = y0; yy < y1; yy++) {
      for (let xx = x0; xx < x1; xx++) {
        const i = (yy * this.width + xx) * 3;
        this.data[i] = colour[0];
        this.data[i + 1] = colour[1];
        this.data[i + 2] = colour[2];
      }
    }
  }

  pixel(x: number, y: number): Rgb {
    const i = (y * this.width + x) * 3;
    return [this.data[i]!, this.data[i + 1]!, this.data[i + 2]!];
  }
}

function chunk(type: string, body: Uint8Array): Buffer {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(body.length);
  const typed = Buffer.concat([Buffer.from(type, 'ascii'), body]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(typed));
  return Buffer.concat([len, typed, crc]);
}

/** Encode a raster as an 8-bit RGB PNG with no filtering. */
export function encodePng(r: Raster): Buffer {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(r.width, 0);
  header.writeUInt32BE(r.height, 4);
  header[8] = 8; // bit depth
  header[9] = 2; // colour type: RGB
  const stride = r.width * 3;
  const raw = Buffer.alloc((stride + 1) * r.height);
  for (let y = 0; y < r.height; y++) {
    raw[y * (stride + 1)] = 0; // filter: none
    raw.set(r.data.subarray(y * stride, (y + 1) * stride), y * (stride + 1) + 1);
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(raw)),
    chunk('IEND', new Uint8Array(0)),
  ]);
}
