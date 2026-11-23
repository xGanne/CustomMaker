import { PNG } from "pngjs";
import { describe, expect, it } from "vitest";

import { encodePng } from "../src/core/png";
import { createRaster } from "../src/core/raster";

describe("gravação de PNG", () => {
  it("preserva cada byte, inclusive pixels semitransparentes", async () => {
    const raster = createRaster(37, 23);
    for (let i = 0; i < raster.data.length; i++) raster.data[i] = (i * 37 + (i >> 2) * 11) % 256;
    const decoded = PNG.sync.read(Buffer.from(await encodePng(raster)));
    expect([decoded.width, decoded.height]).toEqual([37, 23]);
    expect(new Uint8Array(decoded.data)).toEqual(new Uint8Array(raster.data));
  });
});
