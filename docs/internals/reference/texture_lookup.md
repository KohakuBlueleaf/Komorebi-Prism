# Texture lookup: the card's texture data, looked up per pixel

`prism_reference.material.lookup` looks up the card's texture data (a scene's `texels`,
`mip` and `levels`, as the conversion writes them) by several rules, the card's own among
them. A lookup is split in two: `taps` gives, per pixel, the texels it reads (level,
column, row) and their weights; `gather` sums their values (rgb through a byte table,
`TEXEL_LINEAR` by default, alpha the byte over 255). `reads` and `pages` count what the
taps touch. The check is `python -m checks.texture_lookup`.

## The lookup the card does today

- **The chain.** `scene.public.textures.texture_levels`: an image larger than 1,024
  texels a side is halved (2 x 2 box) until it fits; then each level is the 2 x 2 box of
  the one above, in the stored bytes (sRGB for colour), rounded to bytes, down to 1 x 1.
- **The level, per triangle.** The shade block carries each texture's doubled uv area in
  level-0 texels (`texture.model.triangles.texel_areas`); SETUP compares it with the
  record's doubled screen area (`raster/kernels/passes/shaded.hpp`, `shade_word`;
  the reference's `texture.mip_level`): the level is the count of `k < levels` with
  `texels > area 2^(2k - 1)`, about `round(log2 sqrt(texels / area))`. It is one level for
  every pixel of the triangle (a piece the near plane cuts: the first kept piece's), from
  the geometric mean of the footprint's two axes.
- **The texel.** One per pixel and texture: `x = min(floor(frac(u) W), W - 1)`, `y` the
  same of `1 - frac(v)` and `H` (`pack/rows.hpp`, `key_row`; the reference's
  `texture.texel_xy`), wrapping by the fraction whatever the sampler says. Nothing is
  blended inside a level or between levels.
- **Its page.** The texel's key names its 32 x 32 page of that level
  ([texture model](../material/texture_model.md)); SHADE reads a tile's pages into 128
  slots, a pass of rows at a time.

Under a stretched footprint the level follows neither axis: on a floor or carpet at a
grazing angle the triangle's mean is too fine for its far pixels (the texture is
undersampled and sparkles) and, across a large triangle, wrong for most of them.

## The modes (`taps`)

The footprint is the pixel's two screen derivatives of uv in level-0 texels; their
lengths are the major and minor axis (`footprint`). On the card the derivatives come
from the planes a record already has: with `U = u/z`, `W = 1/z` planes,
`du/dx = (U_x - u W_x) / W` (`plane_derivatives`).

| mode | level | texels a pixel |
| --- | --- | --- |
| `triangle` | the triangle's (`triangle_level`, the card's rule) | 1, `texel_xy` |
| `nearest` | `round(log2 major)`, per pixel | 1 |
| `bilinear` | `round(log2 major)`, per pixel | 4: the 2 x 2 around uv, texel centres at `((x + 0.5) / W, 1 - (y + 0.5) / H)`, wrapping |
| `trilinear` | `log2 major`: bilinear in `floor` and the next, by the fraction | 8 |
| `anisotropic` | `log2 minor'`, `minor' = max(minor, major / most)` | `N = ceil(major / minor')` trilinear lookups (`most` = 8) at `uv + ((i + 0.5) / N - 0.5) axis` along the major axis, averaged: 8 N |

Every lookup filters linear values: each texel's bytes go through the table before the
weights. The chain itself stays the card's (sRGB bytes boxed).

## What a mode needs on the card

- **Per pixel**, beyond today's: the two derivatives (four multiply-adds and the `1/W`
  the record's u and v already use), `log2` of a length (the exponent bits and, for the
  blend, the fraction), and per tap a key and a weight in place of one key.
- **Keys and pages.** SHADE keys one texel a pixel today; bilinear keys 4, trilinear 8,
  anisotropic 8 N, each through the same page scan (`row_addresses`). A 2 x 2 at a page's
  edge reads the next page; trilinear adds the next level's pages.
- **The gather** sums the weighted linear values: today each key is one value to the
  albedo rows; a filtered mode is a multiply-add a tap.

The numbers a pixel and a tile reads on two scenes, and the pictures beside Cycles:
[measurements/texture_lookup](../../../measurements/texture_lookup/README.md).
