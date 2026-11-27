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

- **A slot's own uv.** The triangles store one uv, their material's base-colour texture's
  (its UV set through its transform). Each slot reads `(a u + b v + c, d u + e v + f)` of
  it, the materials file's `uv_maps` (`texture.mapped_uv`; the identity, untouched, for
  the base colour and a slot without a transform of its own); the slot's level-0 texel
  area is scaled by the map's `|a e - b d|` (`texture.map_area`).
- **Normal scale.** A normal texel's x and y are multiplied by the material's
  `normal_scale` before the tangent frame turns it (`texture.normal_scales`), as glTF's
  `normalTexture.scale`.

No bilinear filtering and no level per pixel: one level a triangle, nearest texel.

## Texture accesses

`access` gives the texture pages lit SHADE reads, numbered as the card numbers them:
every level of every texture in pages of `PAGE` = 32 x 32 texels, blocks row by row, one
texture's levels after the other's (`texture_firsts`; `page_groups` gives a page's
texture, level, column and row).

- `shade_pixels`: the pixels each layer's SHADE keys: the opaque and glass layers'
  covered pixels, the masked layer's where its 1/z, as unsigned bits, is above the
  opaque layer's.
- `layer_pages`: per such pixel up to four pages, and each one's texel (its texture and
  level, column and row): the albedo's where the material has an
  albedo texture (any kind), the normal's where it has a normal texture and the
  triangle's frame is valid (not glass), the specular's where it has a specular texture
  and the specular term (lit or transparent with a specular colour), and, in the masked
  layer, a masked material's mask at the albedo's level and texel. The level is the
  triangle's (`shade_setup`), the texel the nearest (`texture.texel_xy`).

It is a module of its own so that `texture` does not import the frames that call it.
