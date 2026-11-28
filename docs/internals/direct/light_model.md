# Direct light: the card's data on the host

`prism.stages.direct.light.model` holds, in numpy, what LIGHT reads and what it should
give: the tangent frame a record's planes give, in float32 as the card's scalar code
computes it; the terms and their bits; the light pages (the shadow map, the background,
the field); LIGHT's table; the sun's region with a camera a quadrant of the shadow map;
and the checks of the surface planes, the lit frame and the shadow map. LIGHT's layouts are
in the texture stage's `kernels/shade.h`, whose constants the model reads from
`prism.stages.material.texture.model.numbers.SH`; the sun region's places are constants of
`model.numbers` (`RF_SUN_*`).

## The surface planes and LIGHT

On a lit frame SHADE is the material stage: per pixel it writes the surface planes instead
of a colour, and LIGHT turns each tile's planes into the three colour planes SHOW reads.

- **The frame's planes.** 1/z (where the masked layer's pixel is taken, its 1/z) and, in
  the triangle's plane, the material word `material | kind << 16 | exponent << 20`
  (`kMaterialKindShift`, `kMaterialExponentShift`); an empty pixel keeps FILL's -1, bit 31
  set.
- **The surface's planes**, two more frames of five laid out as the fill's: `a` (albedo x
  base, linear; emissive x the emissive scale), the normal (scene space, unit), the
  visibility (the light plane's value, the corners carrying the baked visibility), the
  specular colour times its texel (0 without a specular term). `surface.decode_planes`
  turns frame pages into these images; `surface.reference_surface` gives the reference's
  (from `rasterize_lighted`'s parts with the specular and glass terms only, so no shadow
  or lamp is computed).

## The frame from the planes

The card has no per-triangle data in LIGHT: for each triangle that wins a pixel of an
item, its first record's planes of 1/z, u/z and v/z and the camera give the triangle's
normal and its tangent frame (`frame.frame_from_planes`). About the centre (`c' = a cx + b
cy + c`) a pixel's camera point is `(x', -y', f) / (f w)`, 1/z is `m0 . (x', y', 1)`, and
the point is affine in (u, v) through `M = (m0, m1, m2)`. So:

- the normal is `-(a f, -b f, c')` of the 1/z plane, turned to scene space
  (`frame.to_world`: right x + up y + forward z) and made unit;
- `dP/du ~ diag(1, -1, f) (m2 x m0) sign(det M)`, made orthogonal to the normal and unit:
  the tangent; the bitangent is `n x t`, turned toward `+v`
  (`diag(1, -1, f) (m0 x m1) sign(det M)`);
- the frame is valid where `det M` and the tangent are not 0.

Lengths are inverted by `frame.rsqrt`: the cores have no divide, so 1 / sqrt(x) is the
estimate `0x5F3759DF - (bits >> 1)` and three Newton steps of multiplies and adds, each
rounded in float32 as the card rounds it (`frame.unit`: zero where the length is zero).
Against the reference's frame (`shade_setup`), a handful of records whose uv determinant
is exactly 0 have a non-zero float32 `det M`; the host marks those triangles
(`kShadeNoFrame`, the texture model), so the card takes the triangle's normal there as the
reference does. `expect.frame_check` measures the angles between the two frames over
sampled records, whole triangles and first pieces of cut ones apart
(`frame.angle_degrees`, `frame.figures`).

## The terms and their bits

LIGHT computes, per pixel, `E = max(0, sky(n)) x vis + ambient + sun x max(0, n.s) x
shadow + the lamps`, the colour `a / pi x E` plus the Blinn-Phong term for the sun and each
lamp where the specular plane is not 0; `emissive` pixels take `a`, empty ones the
background; then the tone step. Sky, ambient and the sun are always on (`BASE_TERMS`); the
others are bits of the table's terms word (`terms.term_bits`, shade.h `kTerm*`):

| term | bit |
|---|---|
| shadow | 1 |
| lamps | 2 |
| specular | 4 |
| background | 8 |
| indirect | 16 |

The reference's `glass` term has no bit: the glass layer's own command does it. With
`indirect` the field's irradiance takes the place of `sky x vis + ambient`; clearing its
bit (`light_table(..., indirect=False)`) switches the field off with its words and pages
kept.

## The light pages

The maps LIGHT samples are one array of pages of 32 x 32 values (`terms.light_pages`):
the shadow map's 1/z, then the background's octahedral map as three planes (red, green,
blue), each a map cut into pages row by row, a page's values row by row from the top
(`terms.map_pages`); with the field, its pages after them (`terms.light_pages_first`). A
shadow map of side 1,024 is 1,024 pages, of 2,048 4,096; the octahedral map's planes 256 or
4,096 pages each. Per pixel the vector unit forms four shadow texel keys (the point moved
one shadow texel along n into the sun's camera, the 2 x 2 filter's corner and fractions; a
tap outside the map reads key 0, a texel of 1/z 0: lit), or on an empty pixel the
background texel of its view direction turned by `-turn` about y in each channel. The
pages a row needs (at most 128) go into SHADE's page slots by the same mechanism.

With the option `shadow_transmit` and glass in the scene (`model/transmit.py`), the
sun's map keeps its `T` (the reference's kept form, `prism_reference.direct.transmit`)
after every other part: a map tile's block of 16 x 16 codes (a byte grey, a word RGB,
channels chosen once from the materials), blocks in the map's tile order, 16 or 4 to a
page (`core/include/thread/transmit.h`); the pages start at 255 (T 1). The DEPTH views
that draw the map draw the glass layer too (the shadow host names the layers in slot
`view.depth`) and write the blocks: in a tile thread the material step's glass layer
makes T in its colour pages and the depth step pushes the band's codes; in the default
form SHADE's transmit mode (`kShadeTransmit`) puts them in the opaque frame's plane 1
(its writer writes that plane besides the 1/z and the material word) and COPY_TRANSMIT
(after COPY) writes T 1 over every tile, then the codes of the glass layer's items that
are not empty (an empty item is a tile without glass: T 1 stays). LIGHT finds a shadow tap's T from its key (the page its map tile, its
texel's row and column halved), gathers it with the taps, and weights each lit tap by it
before the bilinear sum, a channel each (shine and the colour per channel).

Every part of it is built only with the option on: the defines `PRISM_LIGHT_TRANSMIT`,
`PRISM_SHADE_TRANSMIT`, `PRISM_SHOW_TRANSMIT` and the thread's `POST_SHOW_TRANSMIT` in
the default form, the tile thread `LIT_TRANSMIT` (`GI_TRANSMIT`) of the threads' form,
whose steps are the lit ones built with T (`material_transmit.hpp`,
`light_transmit_step.hpp`, depth out with its T words). Off, the kernels are those of a
build without it. The channels are read once a tile into the pass's numbers (a code's
mask and its spread to three channels, a texel's place); a grey T is three equal
channels from there on, so the rows run one body. The taps' addresses and codes take
4,096 words and the tile's numbers 8 more after them (kept in L1, not on the pack CPU's
stack, whose margin is the narrowest): LIGHT's work words after the field's corners in
both forms, the tile thread's light step asking for a keep `work` larger by 16,416
bytes.

## LIGHT's table

4,096 bytes (`kLightTableBytes`; `table.light_table`), float32 unless said:

| words | what |
|---|---|
| 16 c + 0 to 8 | channel c's sky terms: `C4 k0 - C5 k6`, `C3 k6`, `C1 k8`, `2 C1 (k4, k7, k5)`, `2 C2 (k3, k1, k2)` of the sky's 9 SH coefficients |
| 16 c + 9, 10 | channel c's ambient, sun irradiance |
| 48 to 50 | the sun's direction |
| 51, 52 | exposure, exposure / pi |
| 53 to 55 | FILL's background |
| 56 | 1 / pi |
| 57 | int: the terms' bits |
| 58 | int: the bits of the largest specular exponent (the power by squaring) |
| 59 | int: the lamps (0 without the term), at most 32 |
| 60, 61 | a shadow texel's world size; the shadow bias as 1/z |
| 62, 63 | cos and sin of `-turn` (the background's turn about y) |
| 64 to 79 | the sun's (shadow) camera |
| 80 to 82 | the shadow map's first page plus one, its pages a row, its side |
| 83 to 86 | the octahedral map's first page plus one, pages a row, side, side - 1 |
| 87 | int: a background channel's key step, its pages << 10 |
| 88 | int: the light pages in all |
| 89 to 91 | the glass's reflection share, F0 (0.04), 1 - F0 |
| 92, 93 | the tone step's saturation; int: its curve (0 plain, 1 filmic) |
| 94, 95 | int: the map's T's first page plus one (0: none), its channels |
| 96 to 111 | the camera (the reader's copy) |
| 128 + 16 l | lamp l: position, colour, intensity, radius, 1 / radius, size^2, then its shape: axis (3), scale, offset, square (below) |
| 640 to 656 | the field (below) |

A lamp's term is `I max(0, n.l) / (d^2 + s^2) (1 - (d / r)^4)^2` (0 from r on), times
its shape's falloff about its axis: with c = -l . axis (the cosine between the axis and
the way the light leaves the lamp toward the pixel), t = clamp(offset + scale c, 0, 1)
and the falloff `t (square (t - 1) + 1)`: t^2 for square 1, t for square 0
(`prism_reference.direct.lamps.shaped`). A point has scale 0 and no falloff: LIGHT skips
the shape for it (a scalar test of the table's word), so a scene of points pays nothing.
A spot (`spot_shape`) has glTF's cone: scale 1 / max(cos inner - cos outer, 0.001),
offset -cos outer x scale, square 1. An area light's stand-in (`lobe_shape`) is a cosine
lobe about its emitting normal: scale 1, offset 0, square 0, its intensity the light's
power / pi on the axis (the same power over the front half). The stand-in is a point
where the light is a surface: wrong near the light (no penumbra, a hot spot at the
centre), and unshadowed, as every lamp of LIGHT is unshadowed today. Shapes come only
with a file's own lighting (the option `file_lights`), and the stand-ins only with
`area_lights` too (`lights.load`, the host and the reference alike); without them every
lamp is a point, as before. The row was 10
words and is 16 now: the table still holds 32 lamps.

The table lives in the frame thread's sun region, so the host rewrites it between frames
(a moved sun, the tone, the indirect switch) without a load.

## The sun

The sun moves on the host's numbers and the card renders its own shadow map.

- **The scene's box** (`sun.scene_box`): the sun's camera and the shadow texel read only the
  positions' least and greatest corners, so two points stand for the mesh.
- **The moved lights** (`sun.sun_lights`): the reference's `moved` without its shadow map:
  the turn grows by the azimuth's change, the sky's coefficients turn with it
  (`sh_turned`), the new direction, `sun_camera` at the map's side, the texel by
  `shadow_map`'s rule and the bias kept at the same number of texels; at or below the
  horizon the sun's irradiance is 0. The map stays the loaded array (its shape only is
  read).
- **The sun's path** (`sun.sun_path`): the azimuth moves 15 degrees a step from the start;
  the elevation swings between 25 and 80 degrees by a sine over 24 steps.
- **The quadrants** (`sun.quadrant_cameras`). The fill renders 1,024 x 1,024; a map of
  side 2,048 is four quadrants, each the 2,048 camera with its principal point moved by
  `(-1024 i, -1024 j)`, quadrant (i, j) the (j n + i)-th, n the quadrants a side (the
  side over 1,024, whatever the side). The map's pages are one grid of pages row by row (`map_pages`),
  so in a map of side 2,048 a quadrant's tile at row r, column c lands at page
  `32 i + 2048 j + 64 r + c`, and LIGHT's lookup does not change with the side.
  `sun.shadow_of_pages` is the inverse.
- **The sun region** (`sun.sun_region`, 8,192 bytes, `RF_SUN_BYTES`): from byte 0 a camera
  page a quadrant, 64 bytes apart (`RF_SUN_CAMERA_BYTES`, 16 words of the camera), COUNT's
  and SETUP's camera for that pass; at byte 256 (`RF_SUN_ACROSS_AT`) the quadrants a side;
  from byte 4,096 (`RF_SUN_TABLE_AT`) LIGHT's table. The four camera pages before byte 256
  are as many quadrants as this layout holds; a map of more is refused here (the thread's
  sun pass of `direct.shadow_pcf` lays its region out by the quadrants instead).
- **The lists** (`sun.sun_entries`): the sun sees the whole scene, so each layer's list
  entries in a sun view are bounded at the load over sampled suns: per triangle the tiles
  of its screen box (setup's box rule, the binning's tiles, zero areas counted), the most
  over the suns and quadrants.

## The field as LIGHT reads it

The reference's indirect term is a voxel field of irradiance, 6 directional colours a
voxel, looked up at `P + n h/2` with trilinear weights over the 8 voxels around it,
renormalised over those with data, the three directions n faces blended by `n_a^2`; where
no voxel has data, the ambient.

- **The texels** (`pack_field`): one 32-bit word a (voxel, direction): bit 31 has data,
  red 11 bits, green 11, blue 9, each `round(sqrt(v / scale) (2^b - 1))`, the scale the
  field's largest value. `field.field_of` packs the reference's field (`field_for`, the
  bounce passes and the field's weights) for the lights.
- **The pages** (`field.field_layout`, `field.field_pages`): a page is a block of 8 x 2 x 8
  voxels (x, y up, z; `kFieldBlock*`) times 6 directions, texel `d 128 + (y 8 + z) 8 + x`;
  blocks in x, then z, then y, dense over the field's box padded to whole blocks, 0 (no
  data) where a voxel is not in the field. The pages follow the shadow and background
  pages in the light pages.
- **The table's words** (`field.field_words`, 640 to 656): the origin, `h / 2`, h, 1 / h,
  the dims, the blocks a row and a layer (x, x z), the first page plus one, a channel's
  unit `scale / (2^b - 1)^2`, the scale, int the field's pages.

## In a tile thread

The threads' form lights a tile with the same table, pages and field as the light step
(`steps/step.py`, [steps, kinds and the tile thread](../program/steps.md)): after the lit
material step, on the planes left in the core's memory (`frame.surface` and the first
layer's `frame.visibility`), a quarter tile at a time, into the first layer's colour
planes (the displayed form, or with glass the linear then the glass form). Its begin
reads LIGHT's table with the view's camera into its kept table page once a command, and
the field's version the frame's thread gave. Its light pages are asked through the loop's
request rings. Its words of the frame's page (`light_frame_words.c`): the table (the sun
region's, through slot `light.shadow_map`), the light pages, the glass layer, and with the
job thread (`direct.light.threads_field`) the field's version from the slots
`light.field` and `light.field_scale`: 1 + its first page for the half of the field's
pages the last update wrote, a channel's unit times the scale, the scale; 0 before the
first update, when the table's own field words hold. So a new field is taken between two
frames, never inside one.

## The checks

All take arrays: the card's planes or picture as the host reads them, decoded.

- **`expect.surface_check`**: the card's surface against the reference's over the pixels
  the reference covers, later pieces of cut triangles apart: `a` and the specular over 2 /
  255, the normal's angle, the visibility over 1 / 255, the material word, and empty pixels
  marked; `all_within` holds when `a`, the visibility, the material words and the empty
  marks agree on every checked pixel. With the glass layer's planes, `expect.glass_check`:
  the glass in front (bit 31 clear and 1/z above the merged surface's) on each side, ties,
  then on both the 1/z relative error, the material and the normal.
- **`expect.light_check`**: the card's 8-bit picture against `rasterize_lighted` (the
  default frame, the 2 x 2 filter, `surface.light_reference`): shares of pixels more than
  2, 4, 8 off in a channel, later pieces apart, the glass in front apart; with the shadow,
  inside and outside the sun's shadow edge band (`surface.shadow_band`: the reference's
  filter strictly between 0 and 1, and the neighbouring pixels), where the card's fused
  multiply-adds and numpy's two roundings flip a tap; with the field, where the lookup
  found fewer than 8 voxels with data (`expect.field_sparse`). `ok` is a share over 4
  under 1 %.
- **`expect.sun_check`**: the card's shadow map against `rasterize_shaded` at each
  quadrant's camera: texels more than 1e-5 relative apart and texels empty on one side
  only, by the reference's layer (opaque, masked, empty) and by quadrant, later pieces
  apart.
