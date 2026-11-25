# Material: texture sampling and the texture accesses

`prism_reference.material`: `kinds` (the material kinds and texture slots), `texture`
(the mip level, the texel address, the fetch) and `access` (which texture pages a frame
reads). SHADE itself, the stage that colours a pixel from its material, is in
`raster.frames` ([raster](raster.md), "Shading").

## Sampling

- **Level.** For a triangle with doubled screen area `A` in pixels and `T` in level-0
  texels, the level is the number of `k = 1 .. levels - 1` with `T > A 2^(2k - 1)`: the
  level at which a pixel is nearest to one texel (`texture.mip_level`).
- **Texel.** The nearest texel, coordinates wrapping, row 0 at v = 1
  (`texture.texel_xy`).
- **Bytes to numbers.** An albedo byte `b` is linear colour `(b / 255)^2.2`
  (`TEXEL_LINEAR`, the pictures' gamma); the other textures' bytes are `b / 255`
  (`TEXEL_UNIT`) and a normal's `2 b / 255 - 1` (`TEXEL_SIGNED`). Lookup tables, so numpy
  and C++ read the same float32 values.

No bilinear filtering and no level per pixel: one level a triangle, nearest texel.

## Texture accesses

`access` gives the numbers a shading pass on the cores is sized by: the texture pages
(`PAGE` = 32 x 32 texels of one level) each layer's pixels read (`layer_accesses`,
`frame_accesses`), how many distinct pages a 32 x 32 tile reads (`per_tile_distinct`,
`histogram`) and the hit rate of a per-core page cache of 8, 16 and 32 pages (`CACHE_PAGES`) under least
recently used replacement (`lru_hits`). It is a module of its own so that `texture` does
not import the frames that call it.
