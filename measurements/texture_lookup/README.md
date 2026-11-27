# Texture lookup: the modes on two scenes, beside Cycles

The base colour of the plain glTF export of italian_flat and lynxsdesign
([the glTF truth](../gltf_truth/README.md)) at the render camera, 1,280 x 720, looked
up in the card's own texture data (the conversion's chains: at most 1,024 texels a side,
2 x 2 boxes of the sRGB bytes) by each mode of `prism_reference.material.lookup`
([texture lookup](../../docs/internals/reference/texture_lookup.md)). The pixel's triangle
and its uv footprint are the surface reference's (the rasterizer's triangle, the
analytic derivatives of the pixel's ray); `triangle` takes the card's level rule through
`setup`'s pieces. The truth of the filtering is the same lookup at 4 x 4 the size
(trilinear) boxed down: it removes what Cycles' picture adds beside the texture (sheen,
the full-size images, the colour transfer). Cycles' diffuse colour pass (64 samples) is
beside it in the pictures. numpy on 8 CPUs, no card, 2026-11-27.

- taps: texels a pixel reads (anisotropic: 8 lookups of 8, the unused ones weigh 0);
  reads: those of weight above 0.
- pages: distinct 32 x 32 texture pages a 32 x 32 tile of the frame touches, over the
  tiles with a textured pixel (SHADE's cache holds 128).
- MAD: the mean absolute difference of the linear base colour to the 4 x 4 lookup, over
  the frame's covered pixels and over a crop.

| scene | mode | taps | reads | pages mean | pages p99 | pages max | MAD frame | MAD crop |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| italian_flat | triangle (today) | 1 | 1.00 | 9.6 | 34 | 40 | 0.0146 | carpet 0.0530, floor 0.0249 |
| italian_flat | nearest | 1 | 1.00 | 8.1 | 30 | 35 | 0.0136 | carpet 0.0423, floor 0.0163 |
| italian_flat | bilinear | 4 | 4.00 | 8.5 | 31 | 35 | 0.0109 | carpet 0.0376, floor 0.0145 |
| italian_flat | trilinear | 8 | 7.97 | 14.0 | 44 | 56 | 0.0102 | carpet 0.0365, floor 0.0143 |
| italian_flat | anisotropic | 64 | 25.86 | 22.4 | 65 | 80 | 0.0054 | carpet 0.0046, floor 0.0075 |
| lynxsdesign | triangle (today) | 1 | 1.00 | 7.1 | 22 | 29 | 0.0130 | armchair 0.0233, cushion 0.0522 |
| lynxsdesign | nearest | 1 | 1.00 | 5.7 | 18 | 25 | 0.0129 | armchair 0.0227, cushion 0.0537 |
| lynxsdesign | bilinear | 4 | 4.00 | 6.2 | 22 | 26 | 0.0082 | armchair 0.0060, cushion 0.0412 |
| lynxsdesign | trilinear | 8 | 7.85 | 10.6 | 31 | 35 | 0.0076 | armchair 0.0056, cushion 0.0419 |
| lynxsdesign | anisotropic | 64 | 19.37 | 16.4 | 49 | 63 | 0.0068 | armchair 0.0051, cushion 0.0346 |

Textured pixels: 507,165 (italian_flat), 706,499 (lynxsdesign).

What the pictures show:

- Today's lookup sparkles where a large triangle is seen at a grazing angle: the carpet
  and the floor behind the chair in italian_flat, the turning edge of lynxsdesign's
  armchairs. The pipeline reference's own textured frame (`raster.frames`, the card's rule
  on the converted scene) shows the same pixels.
- Bilinear and trilinear remove the sparkle and blur those surfaces along the short
  axis (the level follows the long one); anisotropic keeps the carpet's and floor's grain
  as the 4 x 4 lookup and Cycles show it.
- On the fabrics seen face on (the armchairs' fronts, the sofas, the poufs) every mode is
  close to the 4 x 4 lookup; the level per pixel alone (`nearest`) changes little.
- The card's lit picture of lynxsdesign shows a strong pattern of blue and warm patches
  on the armchairs that no mode of the base colour shows, nor the pipeline reference's
  textured frame of the card's rule: it is not the texture lookup.
