# Direct light: the lit frame, its lights and glass

`prism_reference.direct`: `sky` (the environment, harmonics, the octahedral map, the
background), `shadow` (the sun camera, the shadow map, the lookup), `lamps` (point
lights), `visibility` (the per-vertex sky visibility bake), `prepare` (writing a scene's
lights file), `lights` (loading it, the sun's angles, `moved`), `frame` (the lit frame,
`rasterize_lighted`) and `glass` (glass over the surface behind). The tone step and the
8-bit conversion are `post.tone` and `post.display`.

## Lighting

`rasterize_lighted(scene, materials, lights)` in `direct.frame` is SHADE with
direct light in place of the fixed per-vertex shade and the `lit` kind's hand-placed
light: a sun, a sky and point lights at the scene's lamps. It is defined in numpy
only: the C++ version (`native/raster`) does not have it. Every rule is per-pixel arithmetic, a
lookup in a table or a texel fetch, so a per-tile kernel can follow it; no ray is
traced per pixel. The lights and their precomputed data are in `prism_reference.direct`,
the per-scene numbers in the `lighting` entry of `scene/public/public_scenes.json`
([the scenes page](../../concepts/scenes.md)).

```bash
python scripts/data/public_scenes.py lighting sponza      # map, visibility bake, lamps, shadow map
```

writes `$PRISM_DATA/public/<scene>_lighting.npz`; the visibility bake is also kept in
`<scene>_visibility.npz` beside the materials file and reused unless `--rebake`.

1. **Environment.** One HDR environment map per scene (Poly Haven, CC0, the
   `environments` table), turned about the up axis (y) by the scene's `turn` (the
   sun's azimuth changes it: "Moving the sun" below). The
   sun is the brightest small region: the luminance-weighted centre of the excess
   over its surroundings inside 4 degrees of the brightest texel; its colour is that
   excess (luminance 1). The sky is the map with that cone replaced by the mean of
   the ring from 4 to 8 degrees, projected to 9 spherical-harmonic coefficients per
   colour; its irradiance on a normal is the quadratic form of Ramamoorthi and
   Hanrahan (2001), clamped at 0. The sun's irradiance facing it is `sun_to_sky`
   times the sky's irradiance on a horizontal surface (its luminance), in the sun's
   colour. `direct.sky.environment` recomputes these from the file. When the entry has an
   authored `sun` (the direction it shines along, its colour), the sun's direction
   and colour are those; the map is turned about y so its own sun's azimuth equals
   the authored one (`turn` is computed) and the sky still comes from the map with its
   sun removed.
2. **Sky visibility**, baked per vertex: the share of 64 cosine-weighted rays (fixed
   directions per vertex from the hash of `vertex x 64 + ray`) from the vertex, moved
   the scene's `eps` along its area-weighted normal, that leave the scene without a
   hit, traced with the reference ray tracer (`trace.tracer.trace`, any hit). It takes
   the place of the light term at the corners, so the `light/z` plane interpolates it.
3. **Sun shadow.** The 1/z at `shadow_side` x `shadow_side` (the entry's, default
   2,048, saved with the map) from a camera 1000 scene radii away along the sun's
   direction, aimed at the centre of the scene's box, its frame covering the box
   (`sun_camera(..., side)`: focal and principal point scale with the side). A side of
   2,048 is four renders at FILL's 1,024 x 1,024: quadrant (i, j) uses that camera with
   its principal point moved by (-1024 i, -1024 j) (`quadrant_camera`), so its pixel
   (x, y) is texel (x + 1024 i, y + 1024 j). Each render has SHADE's two FILLs and holes: a texel takes the masked layer's 1/z where
   it is nearer and not a hole, else the other layer's, so plants and chains cast the
   shadow of their leaves, not of their quads. A pixel's point, moved along its
   lighting normal `n` (step 5: the normal map's where there is one, else the
   triangle's turned toward the eye) by one shadow texel's world size, is
   shadowed at a texel when its 1/z in that camera is below the texel's by more than
   the bias (`shadow_bias` texels at the camera's distance); texels outside the map
   are lit. The sun's share is the 2 x 2 percentage-closer filter: the comparisons at
   the four nearest texels, weighted bilinearly. One tap (the nearest texel,
   `pcf=False`) left sawtooth edges where the sun grazes a surface.
4. **Point lights.** Emissive triangles connected through shared vertices form
   groups; groups whose centroids are nearer than `merge_distance` are merged. A lamp
   is a point light at its area-weighted centroid, its colour the area-weighted
   emission colour (base colour x the emission texture's 1 x 1 level, scaled to a
   largest channel of 1), its intensity
   `lamp_scale` x its area. Irradiance at distance `d` on normal `n` toward `l`:
   `I max(0, n.l) / (d^2 + s^2) (1 - (d/r)^4)^2` for `d < r`, 0 from `r` on
   (`radius`, `size`). No shadows from point lights.
   When the scene's entry has a list `lights` (authored point lights: position,
   colour), the lamps are those instead, each of intensity `lamp_scale`; the emissive
   groups are used only when `lights` is absent (an empty list: no lamps).
5. **A pixel.** `a` = albedo x base colour as SHADE has it (`flat`: the base colour).
   The normal is the normal map's in the triangle's frame where the material has one
   and the frame is valid, else the triangle's normal turned toward the eye.
   `E = sky(n) x visibility + ambient + sun x max(0, n.s) x shadow + the lamps`;
   colour `= a / pi x E +` the `lit` kind's Blinn-Phong term once for the sun and
   once per lamp, each times that light's irradiance (with `n.l` and the shadow) over
   pi, only for `lit` materials with a specular colour. `emissive`: `a x
   emissive_scale`, unlit; `masked`: holes as SHADE. Background: the nearest texel of
   the octahedral map (below) in the pixel's view direction turned by `-turn` about y,
   `(x, z) -> (c x + s z, c z - s x)` with `c, s` the float32 cosine and sine of
   `-turn` (y kept). The frame is the tone step of the colour (`post.tone.tone`, below),
   then the pictures' 8-bit conversion (`post.display.to_srgb8`, the 2.2 gamma).
6. **Octahedral map.** `prepare` resamples the environment once into a side x side
   (the entry's `sky_side`, default 2,048; a reader takes it from the map's shape)
   float32 RGB map of directions in the environment's own frame (turn 0, y up), saved
   in the lighting file as `octahedral`, so the background needs no trigonometry per
   pixel and a new `turn` changes a number, never the map. A direction
   `d = (x, y, z)` (need not be unit) goes to `u = x / (|x| + |y| + |z|)`,
   `v = z / (|x| + |y| + |z|)`; when `y < 0` these are folded to
   `(u, v) = ((1 - |v|) sign u, (1 - |u|) sign v)` (both from the unfolded values,
   sign 0 counted as +). Its texel is column `floor((u + 1) / 2 x side)`, row
   `floor((v + 1) / 2 x side)`, each clamped to `side - 1`. The inverse, used to fill
   the map at texel centres `u, v = (i + 0.5) / side x 2 - 1`: `y = 1 - |u| - |v|`; when
   `y < 0`, `(u, v)` unfolded by the same rule; the direction is `(u, y, v)`
   normalized, whose nearest texel of the equirectangular map is taken. The sun and
   sky still come from the equirectangular file. The map is 2,048 and the files 4k
   (4096 x 2048) because a frame's pixel at 75 degrees over 1,024 pixels is 0.07
   degrees, a 512 texel about 0.4 and a 1k file's 0.35: the sky was blocky; a 2,048
   texel is about 0.1 and a 4k file's 0.09. (Before the movable sun the map
   was resampled turned and looked up unturned. On the Bistro exterior's own view the
   change moved 15,536 of its 24,108 background pixels, by 7.2 of 255 on average and
   95 at most, from nearest-texel resampling on a differently turned grid; against a
   direct lookup of the file the mean error went from 5.9 to 5.2. No surface pixel
   changed. Sponza and the interior, turn 0, are unchanged.)

**The tone step.** `display = curve(saturate(exposure x colour))` with three numbers a
frame, from the scene's `lighting` entry (`direct.lights.load` returns them; a caller may
override them in the lights): `exposure`; `saturation` `s` (default 1), which makes
`x` into `max(0, lum + (x - lum) s)`, `lum = (0.2126 R + 0.7152 G) + 0.0722 B`, and
is skipped when `s = 1`; `curve` (default 0): 0 is `x / (1 + x)`, 1 the filmic fit
`x (2.51 x + 0.03) / (x (2.43 x + 0.59) + 0.14)` clamped to [0, 1]. All float32 in
that order. The 8-bit conversion is the same for both curves. With the defaults every
frame is the earlier one bit for bit. A host test on the frames with indirect light
(2026-11-23) found the filmic curve at exposure 2 to 3 with saturation about 1.15 less
dull; no scene's entry sets these yet, so the defaults stand.

**Moving the sun.** `direct.lights.moved(lights, scene, materials, azimuth, elevation)` takes
the prepared lights (`direct.lights.load`), the scene's mesh and materials, and two angles in
degrees, and returns the lights of a sun at that place without baking visibility again.
The angles are those of the direction toward the sun (`direct.lights.sun_angles`): azimuth 0
at +x, 90 at -z (a right-handed turn about +y, the sense of `turned`), elevation
`atan2(y, sqrt(x^2 + z^2))` above the horizontal plane; the direction is
`(cos e cos a, sin e, -cos e sin a)`. The scenes' own suns: Sponza azimuth 144.08,
elevation 74.53; Bistro exterior azimuth -90, elevation 61.18 (the authored sun).

- **Azimuth** turns the environment with the sun: `turn` grows by the change of
  azimuth, so the map's own sun keeps the sun's azimuth. The sky's 9 coefficients per
  colour are rotated about y (`sh_turned`: the 9 x 9 matrix taking the basis to the
  basis at turned directions, fitted on 128 directions, exact since each band is closed
  under rotation); they agree with projecting the turned map again to float32 rounding
  (under 6e-8). The background follows through `turn` (step 5). The sky's irradiance on
  a horizontal surface does not change under a turn about y, so the sun's stays.
- **Elevation** moves the sun alone: the sky and the background do not change, so the
  map's own sun disc stays where the map has it (a known inconsistency: the
  background's sun and the light's sun part when the elevation moves).
- **Both** give a new direction and a new shadow map (`sun_camera`, `shadow_map`, the
  same rules); the bias stays `shadow_bias` texels at the new camera's distance. The
  sun's colour and irradiance do not change. At or below the horizon (elevation <= 0)
  the irradiance is 0 and the shadow map is a 1 x 1 map of 0 (all lit, unused).
- At the scene's own angles `moved` returns the prepared lights: the same direction,
  coefficients, turn and shadow map (Sponza bit for bit; the exterior's direction has
  x = 2.95e-17 for -0 and the same shadow map; Sponza at side 2,048 checked again bit
  for bit). Its time is the shadow map's: about 10 s for Sponza, 43 s for the Bistro
  exterior at side 2,048, 4 s and 17 s at 1,024 (numpy, 8 CPUs).

**Terms.** `rasterize_lighted(..., terms=...)` takes a subset of `sky`, `ambient`,
`sun`, `shadow`, `lamps`, `specular`, `background` (default: all of them, the frame
above). A term left out contributes nothing: without `shadow` the sun is unshadowed,
without `background` an empty pixel has the fill's constant background colour
(0.05, 0.05, 0.08); emissive materials are always drawn. The card's stages are
checked against these subsets.

**Returned arrays.** `colour` (H, W, 3, linear), `display` (the tone step's), `depth` (the merged 1/z)
and `tri` (the visible triangle, -1 empty), and `parts`, each per pixel of the taken
layer: `albedo` (`a`), `normal` (the normal used), `visibility`, `specular`
(specular colour x texel, 0 where the material has none), `material` (-1 empty),
`depth` (the merged 1/z), `layer` (0 the other layer, 1 the masked layer, -1
empty), and the diffuse parts `sky`, `sun` and `points` (`a / pi` x that light's
irradiance; 0 on emissive pixels).

Everything per pixel is float32. Not part of it: shadows from lamps, bounced light
(`ambient` stands in for it; the optional term `indirect` replaces it: "Indirect light").
Visibility per vertex is coarse on large triangles: Sponza's courtyard floor is a few
triangles whose 23 vertices lie under the arcades, so it gets no sky light.
A shadow texel is 2.25 units on Sponza at side 2,048 (4.5 at 1,024); on a wall the sun
grazes (n.s 0.12 to 0.24) it stretches to about 9 to 19 units (19 to 37), so shadow
edges there are still steps. Turning Sponza's sun by 0.01 / 0.05 / 0.2 degrees changes
10.4 / 10.5 / 11.9 % of its default view's surface pixels by more than 8 of 255 at side
2,048, 11.3 / 11.0 / 13.1 % at 1,024; outside the pixels within 2 of a shadow edge in
both frames 2.2 / 1.6 / 2.1 % against 3.1 / 2.2 / 2.7 % (host, 2026-11-23 16:04). The
larger map sharpens the edges but does not settle them: most of the change is at the
edges and in the speckle of the bias's comparisons, which a turn re-rolls.
The quadrants agree with the 2,048 view: a quadrant's 1/z against a float64
evaluation of the triangle's plane on the 2,048 view's texel ray, 3,000 triangles,
median relative error 6.7e-7 (Sponza; 2.9e-6 for the 1,024 map against its own view);
across a quadrant border one triangle's 1/z steps by up to 6e-5 relative (inside a
quadrant one float32 unit), the two renders' own plane rounding, and no seam shows in a
picture of the map.

## Glass

A material whose transmission `tau` (per channel: `1 - Tf`, else `Tr`, else `1 - d`)
is above 0 has the kind `transparent` and keeps `tau` in the materials file
([the scenes page](../../concepts/scenes.md), "Materials"). It is drawn as a third layer
over the surface behind it, in numpy only (`rasterize_shaded` and `rasterize_lighted`
in `prism_reference.raster`); no ray is traced, every rule is per-pixel arithmetic, a
table lookup or a texel fetch.

1. **Three FILLs.** FILL runs a third time over the transparent triangles only; the
   other two layers do not contain them. The surface behind is the merge of the other
   two (masked where nearer and not a hole, as SHADE). A pixel's glass is the nearest
   transparent triangle there, counted only where it is nearer than that surface (the
   fill's rule: larger 1/z, a tie to the lower triangle number); an empty pixel's
   surface is the background, so glass in front of the sky counts. One transparent
   layer: glass behind glass is not shown.
2. **A pixel with glass in front**, `C` the colour behind (the lit colour before the
   tone curve, or the background's radiance), `a` the glass's albedo x base colour,
   `n` its triangle's normal turned toward the eye (no normal map, also in the smooth
   variant), `v` toward the eye:
   `colour = tau C + (1 - max tau) a / pi E + S + F reflection R`. `E` is the glass's own
   irradiance by the rules of "Lighting" (sky x visibility, ambient, sun with shadow,
   lamps); `S` the `lit` kind's Blinn-Phong term for the sun and each lamp with the
   material's specular colour and exponent (always, when it has a specular colour);
   `R` the environment's radiance along `2 (n.v) n - v` (the octahedral map's nearest
   texel, turned like the background); `F = F0 + (1 - F0)(1 - n.v)^5`, `F0 = 0.04`,
   `n.v` clamped at 0; `reflection` the scene's number of its `lighting` entry. Then
   the tone curve as for every pixel. `rasterize_shaded` (no lighting) uses
   `tau C + (1 - max tau) a light` with its light term and no `S` or `R`; on scenes without
   transparent materials its results are unchanged (no third FILL runs).
3. **Shadows.** Transparent triangles cast none: the shadow map is `rasterize_shaded`'s
   1/z, which is the surface behind the glass. The baked sky visibility is not rebuilt:
   it still treats glass as opaque.
4. **Terms.** `glass` (default on): left out, transparent triangles are not drawn. `R`
   needs `background`; `S` needs `specular`. `parts` gains the glass layer's own planes
   where it is in front: `glass_depth` (1/z, 0 elsewhere), `glass_tri` and
   `glass_material` (-1 elsewhere), `glass_normal` (`n`). The other parts, `depth` and
   `tri` stay those of the surface behind. `rasterize_shaded` also returns the glass
   layer (`glass`) and where it is in front (`front`).

Chosen by the pictures (2026-11-23): `reflection` 0.5 in both Bistro scenes (in the
interior 0.25 left the clear bottles and glasses hard to see, rims only; in the exterior
the panes show the curtains behind them and a faint reflection); Sponza has no
transparent material. Transparent triangles: Bistro interior 220,840 (the bottles,
jars and glasses, the counter's display glass, the cash register's), exterior 3,778 (the
buildings' window panes `MASTER_Glass_Dirty` and `_Clean`, the street lights, a menu
sign). The bottles pass 0.95 to 0.97 (the `_02` bottles 0.8 to 1 by channel), the panes
0.8: the bottles read as clear glass with a faint reflection and highlights in front of
their opaque liquid (`Paris_LiquorBottle_01_Glass_Wine`), the windows as glass with the
rooms' curtains behind. No picture showed a material that should be clearly darker.

| view | pixels with glass in front | `rasterize_lighted` before, after (s) | `rasterize_shaded` before, after (s) |
|---|---:|---:|---:|
| Bistro interior overview | 5,910 | 9.7, 10.2 | 8.5, 8.7 |
| Bistro interior close | 15,416 | 9.2, 9.5 | 7.4, 8.4 |
| Bistro exterior overview | 30,498 | 14.8, 15.9 | 13.8, 15.7 |
| Sponza overview | 0 | 5.6, 5.7 | 4.8, 4.6 |

Numpy, one process pinned to 8 CPUs, 2026-11-23. Outside the glass the lit frames are
unchanged in the interior (the sun's new shadow map differs in 883 of 1,048,576 texels,
none on a visible surface) and in Sponza (bit for bit, both functions); in the exterior
7,942 pixels of the overview change because the sun now passes through the window
panes (1,803 texels of its shadow map). Not represented: refraction, glass behind
glass, coloured shadows (transparent triangles cast none). The C++ version
(`native/raster/shade.hpp`) has no kind 5 yet: on the Bistro scenes a comparison with it
needs that first. The card's texture stage has it (its glass form).

The sun camera's axes (right = y x forward, `direct.shadow.sun_camera`) stay as the shadow
maps were first made with them, not the view cameras' forward x y.
