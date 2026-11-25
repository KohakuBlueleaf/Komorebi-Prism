# Texture: the card's data on the host

`prism.stages.material.texture.model` holds, in numpy, what SHADE reads on a shaded or lit
frame and what it should give: the shade blocks beside the raster stage's mesh blocks, the
textures as pages, SHADE's table, the layers of a scene (opaque, masked, glass), and the
check of the shaded frame against the reference. The layouts come from
`kernels/shade.h`; `model.numbers` reads its constants through `prism.core.headers`, and
every module takes them from there. LIGHT's table and terms live in the same header; the
direct-light stage's model (`docs/internals/direct/light_model.md`) reads them from this
stage's `numbers.SH`.

## The mesh and the shade blocks

A shaded frame loads the mesh as the raster stage lays it out
(`prism.stages.raster.model.records.mesh_blocks`), de-indexed, with each corner's colour
replaced by its texture coordinates u, v and its light term (the baked visibility on a lit
frame). Flat triangles keep their vertex colours on an unlit frame; a lit frame replaces
them all. SETUP then gives every record planes of u/z, v/z and light/z where the plain
frame has colour planes.

Beside each mesh block of 32 triangles is a shade block of 128 words, four rows of 32
(`triangles.mesh_blocks`):

| row | words | what |
|---|---|---|
| 0 | 0 to 31 | the albedo texture's doubled uv area in level 0 texels, float32 |
| 1 | 32 to 63 | the material word |
| 2 | 64 to 95 | the normal texture's doubled area |
| 3 | 96 to 127 | the specular texture's doubled area |

The areas (`texel_areas`) are `|du1 dv2 - du2 dv1| x width x height` of level 0 of each
texture (0 where not finite); SHADE compares them with the pixel's area to choose a mip
level, as the reference's `mip_level` does. The material word is the material index with,
at bits 16, 20 and 24, the number of levels of the albedo, normal and specular textures
(1 where the material has none); SETUP copies it into record word 30 (`kRecShade`). On a lit
frame a triangle whose coordinates give no tangent frame (the reference's `frame_ok`,
`triangles.frame_ok`: the uv determinant is 0 or the tangent vanishes), and every
transparent one, also carries `kShadeNoFrame` (bit 28): its pixels take the triangle's
normal and no normal texture. The camera is left out of `frame_ok`: turning the normal
toward the eye does not change the tangent.

## A texture page and a texel's key

Every level of every texture is cut into blocks of 32 x 32 texels, a 4,096-byte page each
(`kTexPageBytes`; `textures.texture_pages`): RGBA8 words as stored, rows from the top,
blocks row by row, the edge blocks padded by repeating the last row and column. All pages
of all textures are one array; per (texture, level) the model keeps the first page, the
width and the height.

A texel's key is `(1 + page) << 10 | texel`, in 30 bits; the masked layer tags bits 30 and
31. So at most 2^20 - 1 pages (`KEY_PAGES`); `layers.prepare` refuses a scene beyond it.
For a tile SHADE finds the pages its pixels fetch, reads them into 128 page slots in L1
(`kShadeSlots`, and one more holding the white texel) and fetches the texels there; a tile
needing more pages is shaded in several passes of rows.

## SHADE's table

One table of `kShadeTableBytes` (32 KB) in L1, written once a load (`table.table`), word by
word:

| words | what |
|---|---|
| 0, 1, 2 | materials, (texture, level) entries, pages |
| 16 to 271 | `TEXEL_LINEAR`: an albedo byte as linear colour |
| 272 to 527 | `TEXEL_SIGNED`: a normal byte in [-1, 1] |
| 528 to 783 | `TEXEL_UNIT`: a byte in [0, 1] |
| 784 to 786 | FILL's background colour |
| 800 to 815 | lit: the reader's copy of the camera |
| 816 on | a row of 18 words a material, then 2 words an entry |

A material's row (`kMaterialWords`):

| word | what |
|---|---|
| 0 | kind, and at bit 8 one plus the albedo's level 0 entry (0: no albedo) |
| 1 to 3 | base colour |
| 4 | one plus the mask's entry (0: none, or no albedo) |
| 5 | one plus the normal's entry |
| 6 | one plus the specular's entry |
| 7 to 9 | lit base: the base colour, an emissive one times the emissive scale |
| 10 to 12 | specular colour where the material has the Blinn-Phong term, else 0 |
| 13 | the specular exponent where it has the term, else 0 |
| 14 to 16 | transparent: the transmission tau, else 0 |
| 17 | transparent: 1 - max tau, else 1 |

An entry is the (texture, level)'s first page, then `width | height << 16`; texture `t`'s
level `l` is entry `t x levels + l` (levels the most any texture has, 11), so the material
row names a texture by its level 0 entry plus one. The table needs 816 words, 18 a
material and 2 an entry; `table.table` refuses a scene beyond `kShadeTableBytes` with both
numbers.

- **The mask** is fetched at the albedo's place and level, so a masked material's mask
  texture must have the albedo's levels and sizes; `table.table` refuses one that has not.
- **The specular term** (`table.specular_term`): a lit or transparent material with a
  specular colour above 0. Only those carry a colour and an exponent; the exponent
  (`table.exponents`) must fit the material word's 11 bits from bit 20 (`kExponentMax`).
- **Transmission** (`table.transmission`): the materials file's tau where the kind is
  transparent, 0 elsewhere and in a file without it.

## Layers

A scene with masked or transparent triangles is loaded as up to three meshes
(`layers.prepare`): the triangles of every other kind, the masked ones and the
transparent ones, each in triangle order (`layers.layer`) with its own mesh and shade
blocks; the textures and the table are shared. A scene without them is one mesh. `prepare`
on a lit frame takes the corner light terms from the lights' baked visibility and scales
emissive bases by the lights' emissive scale.

- **The masked layer.** Its SHADE reads its own planes and the opaque layer's of the same
  tile, drops the pixels where the opaque layer is nearer (a tie to the opaque layer),
  shades the rest, and writes its own colour where the alpha byte (the mask texture's, or
  the albedo's) is at least 128 (`kAlphaOpaque`), the opaque layer's elsewhere. A hole
  shows the opaque layer, never a second masked surface.
- **The glass layer.** Glass casts no shadow and is left out of the other two meshes.
  Unlit, a third SHADE blends `tau C + (1 - max tau) colour` where the glass is in front
  (`kShadeGlass`); lit, its SHADE writes the glass surface's own planes, which LIGHT's
  glass command reads.

## The check

`expect.check` compares the card's 8-bit picture with the reference's shaded picture of the
same view on `as_shaded(materials)`, the lit kind shaded as textured (no lighting), the
masked kind with its holes. A pixel differs when a channel is more than 2 apart.

Each piece of a triangle the near plane cuts is shaded on the card with its own u/z, v/z
and light/z planes, while the reference uses the first kept piece's planes for all of
them. Both are the same plane in exact arithmetic, but float32 rounds them apart by about
a texel, so those pixels (`layers.later_pieces`: on a piece after the first, inside its
edges) are counted apart, and the shares are over the others; the glass in front is a kind
of its own, its later pieces apart too. The report gives the counts, the shares, the
largest error, and the differing pixels by kind; it also returns the compared picture and
the true one (lit materials lit).
