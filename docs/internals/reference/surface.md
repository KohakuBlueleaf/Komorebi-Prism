# Surface: the metallic-roughness surface of a described scene

`prism_reference.material`: `brdf` (the model), `tangents` (vertex tangents where a file
has none), `filter` (a texture's mip chain and its filters) and `surface` (the planes of
a [scene description](../../concepts/scene_description.md) per pixel). Lighting is not
here: the surface is judged on its own, against the same planes rendered by Cycles
(`scripts/run/surface_compare.py`).

## The model (`brdf.py`)

Functions of float64 arrays; `n`, `v` (to the eye) and `l` (to the light) are unit.

| function | value |
| --- | --- |
| `f0(base, metallic)` | `0.04 (1 - metallic) + base metallic` |
| `diffuse(base, metallic)` | `base (1 - metallic) / pi` |
| `d_ggx(n_h, a)` | `a^2 / (pi (n_h^2 (a^2 - 1) + 1)^2)`, `a = roughness^2` |
| `v_smith(n_l, n_v, a)` | `0.5 / (n_l sqrt(n_v^2 (1 - a^2) + a^2) + n_v sqrt(n_l^2 (1 - a^2) + a^2))` (height-correlated) |
| `fresnel(f0, v_h)` | `f0 + (1 - f0) (1 - v_h)^5` (Schlick) |
| `brdf(base, metallic, roughness, n, v, l)` | `diffuse (1 - F) + D V F`, 0 where `n_l <= 0` or `n_v <= 0` |
| `dielectric_f0(ior, colour)` | `min(((ior - 1) / (ior + 1))^2 colour, 1)` |
| `albedo_tables()`, `table_at`, `lobe_albedo`, `multiple_scattering` | the single-scattering lobe's albedo split by Schlick's terms, read at `(n.v, roughness)`; `f0 Ea + f90 Eb`; `1 + f0 (1 - E) / E` ([described light](described_light.md)) |
| `valid_normal(n, ng, v)` | the shading normal bent so the view's mirror direction stays above the triangle's plane (Cycles' `ensure_valid_specular_reflection`) |
| `d_charlie(n_h, r)`, `v_neubelt(n_l, n_v)`, `sheen_table`, `sheen_scale` | the sheen: `(2 + 1 / a) sin^(1 / a) / (2 pi)` with `a = r^2` (at least `0.07^2`), `1 / (4 (n_l + n_v - n_l n_v))`, its albedo and the scaling of the layers under it |

The only floor is on `a` in D and V: `a >= 1e-6` (`1e-3` squared). Nothing else is
clamped.

The model is not energy conserving away from the normal. With base 1 and metallic 0, the
diffuse lobe weighted by `1 - F(v.h)` and the specular lobe weighted by `F` sum to more
than 1 when the view is far from the normal and the roughness is low. The check judges
the white furnace with the view along the normal (every value at most 1 + 1e-3) and
prints the integrals off the normal beside it (64 x 256 cosine-weighted points, base 1):

| metallic | roughness | 30 degrees | 60 degrees | 80 degrees |
| --- | --- | --- | --- | --- |
| 0 | 0.1 | 0.9992 | 1.0090 | 1.0043 |
| 0 | 0.2 | 0.9995 | 1.0260 | 1.2518 |
| 0 | 0.3 | 0.9992 | 1.0253 | 1.2195 |
| 0 | 0.5 | 0.9962 | 1.0109 | 1.0818 |
| 0 | 0.7 | 0.9877 | 0.9934 | 1.0212 |
| 0 | 1.0 | 0.9731 | 0.9761 | 0.9860 |
| 1 | 0.1 | 0.9925 | 0.7653 | 0.1556 |
| 1 | 0.2 | 0.9979 | 0.9952 | 0.8317 |
| 1 | 0.3 | 0.9888 | 0.9748 | 0.9019 |
| 1 | 0.5 | 0.9041 | 0.8572 | 0.8552 |
| 1 | 0.7 | 0.6920 | 0.7039 | 0.8072 |
| 1 | 1.0 | 0.3351 | 0.4505 | 0.6669 |

On a grid of 2,048 x 4,096 points, metallic 0 at roughness 0.2 gives 1.0166 at 1.0 rad
(57 degrees) and 1.3165 at 1.4 rad (80 degrees): the excess belongs to the model, not to
the grid. At metallic 1 and roughness 0.1 the 64 x 256 grid does not resolve the lobe
(the 80-degree value is low for that reason; the fine grid gives 0.998 at 1.4 rad).

## Tangents (`tangents.py`)

Used only where a primitive carries no `TANGENT`; a file's own tangents are used as they
are (in world space: `xyz` through the copy's matrix, `w` times the sign of its
determinant). Per triangle the derivatives of the position along `u` and along `v` are
solved from its uv differences; they are summed into the corners, each weighted by the
corner's angle. A vertex's tangent is its sum along `u` made orthogonal to the normal and
unit (any perpendicular when that sum vanishes). `w` is +1 when `cross(n, t)` runs along
`-v`, the image's up in the description's uv (origin at the top left), else -1: a
mirrored uv map gives -1. The uv set is the normal texture's.

## The filter (`filter.py`)

`Texture(pixels, role)` holds a mip chain of `(H, W, 4)` float32 levels: grey is spread
to rgb and a missing alpha is 1. In the colour role (base colour, emission) rgb is the
standard sRGB transfer undone before the first level; in the data role (normal,
metallic-roughness, occlusion) the bytes are `b / 255`. Each level is the 2 x 2 box of
the one above (an odd row or column is dropped, a side of 1 stays 1), down to 1 x 1.
`Texture.of_image` decodes a description `Image` with `scene.public.textures.decode_image`.
There is no cap on the size.

Coordinates: a texel `(x, y)` of a `W x H` level has its centre at
`((x + 0.5) / W, (y + 0.5) / H)`, row 0 at `v = 0`. The wrap modes `REPEAT`, `CLAMP` and
`MIRROR` (mirrored repeat) act on integer texel coordinates; the default sampler repeats.
The sampler's filter fields are not read.

The footprint of a pixel is its two screen derivatives of uv, `duv_dx` and `duv_dy`,
in level-0 texels; their lengths are the major and minor axis.

| filter | rule |
| --- | --- |
| `nearest` | the level-0 texel holding uv; no mip level |
| `trilinear` | `lod = log2(major)`; bilinear in levels `floor(lod)` and the next, blended by the fraction; `lod` clamped to the chain |
| `sample` (anisotropic) | `minor' = max(minor, major / most)`, `lod = log2(minor')`; `N = ceil(major / minor')` taps (at most `most`, 16) at `uv + ((i + 0.5) / N - 0.5) axis`, `axis` the longer derivative; their trilinear values averaged |

## The planes (`surface.py`)

`surface(scene, camera_node, size, filter="anisotropic")` returns `(H, W, ...)` planes:

| plane | value |
| --- | --- |
| `covered` | bool: a triangle covers the pixel's centre |
| `depth` | the distance along the view axis |
| `position` | the world position where the pixel's ray meets the triangle's plane |
| `geometric_normal` | the unit face normal of the winding (flipped like `normal`) |
| `normal` | the vertex normals interpolated and made unit, then the normal map: `(x s, y s, z)` of the texel `2 b - 1` (`s` the normal scale) through `(t, cross(n, t) w, n)` (`t` interpolated, made orthogonal to `n`), made unit; both flipped toward the camera when the material is double sided and the pixel sees the back |
| `base_color`, `alpha` | the factor x the base-colour texture x `COLOR_0` (when the primitive has it) |
| `metallic`, `roughness` | the factors x the metallic-roughness texture's B and G |
| `occlusion` | `1 + strength (R - 1)` of the occlusion texture, 1 without |
| `emissive` | the factor x the emissive strength x the emissive texture |
| `material` | int32: the material's index; -1 where not covered, -2 for a triangle without a material (glTF's default material) |
| `transparent` | bool: the nearest surface is `BLEND` or has `KHR_materials_transmission` above 0 (that surface is still shown) |
| `uv` | `uv0` (the description's convention), 0 without |
| `specular_colour` | the dielectric f0: `dielectric_f0` of `KHR_materials_ior` (1.5 without) and `KHR_materials_specular`'s colour factor x its colour texture (sRGB) |
| `specular_weight` | `KHR_materials_specular`'s factor x its texture's alpha, 1 without |
| `sheen_colour`, `sheen_roughness` | `KHR_materials_sheen`'s colour factor x colour texture (sRGB) and roughness factor x roughness texture's alpha; 0 without |

A texture whose primitive lacks its uv set counts as white. `MASK` is not cut: the pixels
under the cutoff are counted (`report["mask_below_cutoff"]`). The report also names, per
primitive with a normal texture, whether its tangents came from the file or were
computed.

Visibility is the rasterizer's (`raster.frames.rasterize`) on the scene drawn by
`flatten` (at most 40,000,000 triangles) and the camera: the node's world axes as they
are, so a rolled camera keeps its roll, the focal length `(H / 2) / tan(yfov / 2)` and
the principal point at the centre, with two exceptions the sidecar gives the render
camera (`material.surface.lens`): the sensor fit keeps the field of view of one side
(`AUTO`: the longer side at each size). `yfov` holds at the camera's `aspect` `a`, so the
fitted side's half-angle tangent is `t = tan(yfov / 2) a` when that side was across at
`a`, else `tan(yfov / 2)`, and `f = (S / 2) / t`, `S` the fitted side in pixels at the
drawn size (W across, else H); a lens shift moves the principal point to
`(W / 2 - shift_x S, H / 2 + shift_y S)`; the near distance is the camera's `znear`, else
`1e-4` of the scene's diagonal. Only the triangle number of a pixel is taken from it.
Everything else is computed in float64 from the pixel's ray
`d = forward + right (x + 0.5 - W / 2) / f + up (H / 2 - y - 0.5) / f` through the
triangle's plane: `t = ((p0 - eye) . n) / (d . n)` is the depth, the barycentrics come
from the hit point, and their screen derivatives from `dP/dx = t right / f + (dt/dx) d`
(likewise for y with `-up / f`). Attributes and their derivatives are interpolated with
them, so every value is perspective-correct and the footprint is analytic. A texture
transform is applied to the corners' uv.

## The comparison (`scripts/run/surface_compare.py`)

For a scene of `$PRISM_DATA/artist/<key>/`: the reference's planes at the sidecar's
camera and 1,280 x 720 against Cycles' planes of the same `.blend` at the same size
(`scripts/blender/planes.py`: the passes of `truth.exr`, 64 samples, normals and positions
turned to +Y up). Written to `<key>/surface/`: each plane of both sides as a PNG
(`ref_*`, `cycles_*`), the differences (`diff_normal`: the angle, 0 to 30 degrees;
`diff_position`: log10 of the distance over the diagonal, -6 to -1; `diff_base_color`:
the mean absolute difference, 0 to 0.25) and `compare.json`:

| key | numbers |
| --- | --- |
| `registration` | over pixels covered on both sides (Cycles: depth under 1e9), the position's distance over the scene's diagonal (median, 99th percentile), the share of all pixels covered on one side only (Cycles shows a surface where its depth is under 1e9 or its Normal is not zero), the share where Cycles shows a surface without a position (`no_position`), the share registered (distance at most 1e-3 of the diagonal) |
| `disagreeing` | the pixels where the two sides do not show the same thing (covered on both, not registered; or shown on one side only), the twenty largest groups by the reference's node and by Cycles' object (Object Index, with the object's type) |
| `not_exported_pixels` | each object of the sidecar's `not_exported.objects` that Cycles' Object Index shows: its name, type, reason and pixels |
| `normal_degrees` | the angle between the two normals over registered pixels (50th, 90th, 99th percentile) |
| `base_color` | against Cycles' `diffuse_color + glossy_color` where the reference's metallic is under 0.01, over registered pixels: the mean absolute difference a channel, PSNR (peak 1) and the pixels; for each filter |
| `aliasing` | per filter, the mean absolute difference of the base colour to the same filter at four times the size, box-filtered down, over pixels covered at both sizes in every sub-pixel |
| `surface`, `tangent_primitives` | covered, transparent and masked pixels, materials seen, textures decoded, the tangents' source per primitive |
| `seconds` | each step |

A scene drawing more than the triangle budget is written with `skipped` and both numbers.

Cycles' passes are the averages of a pixel's samples over its filter: at an edge the
position, normal and colours mix both sides, so the 99th percentiles hold the edges.
The export rewrites
every material as a plain Principled BSDF ([artists' scenes](../../guides/artist_scenes.md));
a material of class X keeps only its viewport colour.
