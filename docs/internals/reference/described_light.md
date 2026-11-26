# Described light: the direct light of a described scene, in units

`prism_reference.direct.described`: `units` (the description's lights as radiometric
numbers), `sample` (the fixed sample sets) and `direct` (the shadow rays and the three
planes); `prism_reference.post.described` (the display). It lights the
[surface](surface.md) of a [scene description](../../concepts/scene_description.md) with
the description's own lights, point, spot, sun, area and world, in their units, and is
judged against Cycles' direct-light passes of the same `.blend` and camera
(`scripts/run/light_compare.py`). Indirect light is not here.

## Units (`units.py`)

Every value is per colour channel, linear, in watts: what Cycles calls a light's
strength in its scene values. `LUMENS_PER_WATT = 683` is Blender's glTF exporter's
`PBR_WATTS_TO_LUMENS`.

| light | the description holds | radiometric value | what Blender's exporter wrote |
| --- | --- | --- | --- |
| point | `intensity` in candela | `I = colour x cd / 683` (W/sr) | `cd = P / (4 pi) x 683 x 2^exposure` from the light's power `P` (watts), `colour` the light's colour (times its emission node's colour and the temperature colour) |
| spot | candela, `inner_cone`, `outer_cone` | `I` as a point times glTF's cone `t^2`, `t = clamp((cos a - cos outer) / max(cos inner - cos outer, 1e-3))`, `a` the angle off the spot's axis | the same intensity (Blender's spot is a point light's power cut by the cone, not concentrated); `outer = spot_size / 2`, `inner = outer (1 - spot_blend)` |
| sun | `intensity` in lux | `E = colour x lux / 683` (W/m^2 on a plane facing the sun) | `lux = strength x 683 x 2^exposure`, the strength in W/m^2 |
| area | the sidecar's `power` (W), `shape`, `size`, matrix | `L = colour x P / (pi A)` (W/(m^2 sr)), one side, Lambertian | `power = energy` as Blender holds it, `size` = (`size`, `size_y`), the matrix in glTF's axes |
| world | the sidecar's `color`, `strength`, `environment`, `rotation` | `L(d) = strength x colour`, or `strength x` the map's texel toward `d` | the Background node's colour and strength, the Environment Texture's image and the Mapping node's rotation |

The exporter runs in its default lighting mode (`SPEC`, "Standard": physically based
glTF units); `scripts/blender/export.py` does not set it. `sidecar.py` reads `power`
into the light's `intensity` and the shape and size unchanged.

An area light's axes: the sidecar's matrix is Blender's world matrix turned into glTF's
axes (`A M A^-1`, `A (x, y, z) = (x, z, -y)`), so Blender's local axes appear in it as
`A` of themselves. The light emits along Blender's local -Z, which is `-(M (0, 1, 0))`
in the description; its sides run along `M (1, 0, 0)` (`size`) and `M (0, 0, -1)`
(`size_y`), the matrix's scale kept. `SQUARE` and `DISK` use `size` for both sides
(Blender ignores `size_y` there); `DISK` and `ELLIPSE` take `size` as diameters and
`A = pi / 4 x` the rectangle's. A punctual light emits along its node's -Z (glTF).

The world map is looked up as Blender's equirectangular projection, in Blender's axes:
`u = 1/2 - atan2(y, x) / 2 pi`, `v = atan2(z, hypot(x, y)) / pi + 1/2`, row 0 at
`v = 1`, after the Mapping rotation (Euler XYZ, x first) and the nearest texel. The
reference reads Radiance `.hdr` maps only; a world map in another format (an OpenEXR
file) is not carried, and the world then gives no light.

## Samples (`sample.py`)

Fixed sets, the same for every pixel:

- an area light: `AREA_SAMPLES = 16` points, the centres of a 4 x 4 grid over the
  rectangle; for `DISK` and `ELLIPSE` the grid mapped onto the disk by Shirley and
  Chiu's concentric map (it keeps areas, so every point stands for `A / 16`);
- the world: `WORLD_SAMPLES = 64` directions about the shading normal with density
  `cos / pi`: the centres `(u1, u2)` of an 8 x 8 grid as `r = sqrt(u1)`,
  `phi = 2 pi u2`, `z = sqrt(1 - u1)`.

## The direct light (`direct.py`)

`described_lights(scene, folder)` prepares the lights and the world, and lists what it
cannot carry (a light kind or an area shape it does not know, a light's `range`, a world
map it does not read). `direct_light(planes, eye, tree, diagonal, lights, world)` lights
every covered pixel of the surface planes:

- The shading normal and the triangle's normal are both turned toward the eye where
  the triangle faces away from it (Cycles shades both sides of a surface).
- A shadow ray starts at the point moved `RAY_OFFSET = 1e-5` of the scene's diagonal
  along that triangle normal; lengths, cosines and the spot's angle are measured from
  the point itself. It is traced through `trace.batch.trace` (any hit) over the box
  tree of every drawn triangle (`trace.tree.build`, the median cut), every triangle
  opaque and seen from both sides.
- A point or spot light: one ray to the light (`tmax = 1` on the unnormalised
  direction); `w = I cos / d^2` (times the cone for a spot).
- A sun: one ray along the direction toward it, unbounded; `w = E cos`.
- An area light: one ray to each of its 16 points, stopped `LIGHT_END = 1e-4` short of
  it; `w = L cos cos' A / (16 d^2)`, `cos'` the angle at the light (0 behind it).
- The world: one ray along each of the 64 directions, unbounded; `w = pi L(d) / 64`.

`w` is the sample's share of the irradiance (radiance times cosine over the sample's
density); a sample with `w = 0` or below the shading horizon traces no ray. With the
model of `material.brdf` (`f0`, `D`, `V`, `F` of the half vector):

| plane | sum over the visible samples | Cycles' pass beside it |
| --- | --- | --- |
| `diffuse_light` | `w / pi`: the irradiance over pi, before the base colour | Diffuse Direct |
| `glossy_light` | `w D V F / f0`: the specular term over its colour `f0` | Glossy Direct |
| `direct` | `w (diffuse (1 - F) + D V F)`, plus the surface's emission | (Combined) |

`glossy_light` and `direct` are 0 where the shading normal faces away from the eye.
Each plane is also kept by light kind (`kinds`), so one kind is the sum of its lights
alone.

Cycles' Glossy Direct is its specular light over its own glossy colour, the directional
albedo of its specular layer; `glossy_light` divides by `f0` instead. The two agree
where the albedo is near `f0` (a smooth surface seen near the normal) and differ by the
ratio of the two colours elsewhere.

## The display (`post/described.py`)

`displayed(colour, render)`: `colour x 2^exposure`, the view transform, then a
`1 / gamma` power. The code has the `Standard` transform (the piecewise sRGB transfer);
any other (`Filmic`, `AgX`, ...) is named in the notes and the standard transfer used, and
a look other than `None` is named and not applied.

## Cycles' passes (`scripts/blender/light_passes.py`)

Run inside Blender on the scene's `.blend`: the scene's camera at the size given
(resolution percentage 100, no border; `light_compare.py passes` gives the sidecar's
render size scaled to a long side of 1,280, so the picture keeps the scene's aspect), Cycles on OptiX, fixed samples (256 by default)
and seed, no denoiser, no adaptive sampling, `max_bounces = 0`, no render data kept
between runs (`use_persistent_data` off: one scene failed with it on, on a CUDA
address error after the world was removed), the passes Combined,
Depth, Normal, Position, Diffuse Direct, Glossy Direct, Diffuse Color, Glossy Color and
Emission. One render a run, each written as `light/cycles_<run>.exr` and its passes as
`light/cycles_<run>.npz` (normal and position turned to the description's axes):

- `all`: every light that renders and the world;
- one run a light kind present (`point`, `spot`, `sun`, `area`, `world`): the lights of
  that kind alone (the world removed unless the kind is `world`);
- `none`: no light and no world: what the surfaces' own emission lights, which the
  reference does not carry.

The lights as Blender has them (power, colour, radius, spot size and blend, sun angle,
area shape, size, spread, portal, normalisation, shadow, and the light's own node tree:
its Emission node's strength, a Light Falloff's strength feeding it, a colour from a
link such as a Blackbody node) go to `light/blender_lights.json`, with what the viewport
and the render see differently (objects shown in the viewport but hidden in the render,
which the export takes as the viewport shows them; objects casting no shadow; the
camera's shift); `--runs` with no run writes that file alone.

## The comparison (`scripts/run/light_compare.py`)

```
python scripts/run/light_compare.py passes <scene ...> [--size W H] [--samples N]
python scripts/run/light_compare.py compare <scene ...>
python scripts/run/light_compare.py table
```

`compare` reads the scene's `scene.glb`, its sidecar and instance table once (their
modification times go to the record, and any change while they were read), draws the
surface at the size of Cycles' passes (anisotropic filter) and lights it. The pixels
compared are those where the surface comparison's registration holds, its rule stated
again: both sides see a surface (Cycles' depth below 1e9) and the two positions lie
within 1e-3 of the scene's diagonal of each other. Per run, for the diffuse pass
(`diffuse_light` against Diffuse Direct) and the glossy pass (`glossy_light` against
Glossy Direct), on the mean of the three channels: the median and the 90th percentile of
`|ours - Cycles| / (|Cycles| + 1e-3 x the median of |Cycles|)` (where that median is 0,
1e-3 of the mean of |Cycles|), and the ratio of the two pictures' means. Cycles' passes
are not negative; the absolute value matters only after the run `none` is taken off
(below), where noise leaves values on both sides of 0. A run of a kind
compares the reference's planes of that kind; a kind the reference does not have (the
world when its map is not read, `none`) compares zeros. Cycles' passes of every run but
`none` have the run `none` taken off (the passes are sums over the lights): a surface's
emission lights the scene in Cycles and cannot be switched off as a light is, so this
is how the other kinds are switched off on Cycles' side; the run `none` itself is
compared as it is, against zeros, and shows what that light is worth.

It writes, under `artist/<key>/light/`, `<run>_<pass>.png` (ours, Cycles and the
relative difference from 0 to 1 side by side, both pictures scaled by the 99th
percentile of Cycles'), `direct.png` (the reference's `direct` and Cycles' Combined
through the display), `compare.json`, and a copy of the record under
`measurements/reference_light/`; `table` writes that folder's README. Each record lists
the lights by kind on both sides and what the reference does not carry of the scene.
No number is fitted to Cycles: each formula above follows from the units.

## The check

`python -m checks.described_light` (no Blender, no card): a floor quad, a square occluder
above it, one light of each kind and a uniform world. `diffuse_light` of each kind at
floor points against its closed form: a point light's `I cos / d^2`, a spot's cone, a
sun's `E cos`, an area light's `pi L F` with `F` the form factor to a parallel rectangle
(by its corner rectangles, to 1 % with the 16 fixed points), a uniform world's `pi L`
where nothing occludes; and the occluder's shadow edges for the point light and the sun
0.05 inside (dark) and outside (lit) of where the geometry puts them.
