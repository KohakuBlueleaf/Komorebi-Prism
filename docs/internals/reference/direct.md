# Direct light: the lit frame, its lights and glass

`prism_reference.direct`: `sky` (the environment, harmonics, the octahedral map, the
background), `shadow` (the sun camera, the shadow map, the lookup), `lamps` (point
lights), `visibility` (the per-vertex sky visibility bake), `prepare` (writing a scene's
lights file), `lights` (loading it, the sun's angles, `moved`), `frame` (the lit frame,
`rasterize_lighted`), `glass` (glass over the surface behind) and `access` (the light
pages a frame reads). The tone step and the
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
   (x, y) is texel (x + 1024 i, y + 1024 j). The renders are DEPTH views (`depth_view`:
   their 1/z planes set up from the near distance's 1/z, [raster](raster.md)). Each render has SHADE's two FILLs and holes: a texel takes the masked layer's 1/z where
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
Without the DEPTH view's shifted planes, the map's own 1/z was off by a median of 141
units at the texels behind Sponza's wrongly shadowed pixels. The lookup was not the
cause: in float32 against float64, the moved point's offset from the camera is off by
0.01 units, the texel by 0.005, and the receiver's depth by 0.1. As a share of the
pixels the traced sun lights (64 rays over the sun's disk, `shadow_traced`), the 2 x 2
filter wrongly shadowed 14.5 % of Sponza's overview before and 0.14 % after; on
breakfast_room it went from 1.3 % to 1.0 %, on italian_flat_97f97a20ba from 0.29 % to
0.25 % (side 2,048, host, 2026-11-27).
The quadrants agree with the 2,048 view: a quadrant's 1/z against a float64
evaluation of the triangle's plane on the 2,048 view's texel ray, 3,000 triangles,
median relative error 6.7e-7 (Sponza; 2.9e-6 for the 1,024 map against its own view);
across a quadrant border one triangle's 1/z steps by up to 6e-5 relative (inside a
quadrant one float32 unit), the two renders' own plane rounding, and no seam shows in a
picture of the map.

## The sun's edge: filters, cascade and a traced truth

Beside the 2 x 2 filter, the reference holds the sun edge's options, not used by a
preset, to judge them against a traced truth:

- `shadow_filter.filtered_shadow(smap, points, normals, method)`: a box of odd width
  (`{"kind": "box", "width"}`, (width + 1)^2 texel reads; width 1 is the present
  filter), rotated disk taps (`"disk"`, a golden-angle spiral turned per pixel), and
  PCSS (`"pcss"`, a blocker search, then the disk at the radius the sun's angle gives).
  With `"levels": True` the search reads the map's nearest-depth levels
  (`nearest_levels`: each texel the nearest 1/z of 2 x 2 below), on the level where its
  reach spans 4 texels, a tap blocking where that cell's nearest surface is nearer than
  the receiver's nearest in the cell. In a cascade's fine map the search from the near
  plane reaches about 150 texels: 16 taps there miss blockers in one pixel and find them
  in the next (square dark blocks along the penumbra), and a 32 x 32 tile's taps touch
  121 to 220 map pages, against 8 to 14 with the levels.
  With `receiver_plane`, the comparisons follow the receiver's own slope (capped at 10
  texel widths), so a slanted receiver does not count as its own blocker.
- `shadow_cascade`: the eye's seen depth range split (practical split, 0.75 toward
  logarithmic) into cameras with the sun camera's axes and distance, each fitted to
  its slice, the whole map last; a point takes the finest camera it lies in by a
  margin of texels. A fit can be kept: `fitted_camera` widens the slice by a margin (a
  share of its extent on each side), puts the half width on steps of 2^(1/8) and the
  centre on the camera's own texel grid, so a fit made again from nearby corners draws
  the same texels; `kept_cameras` keeps each camera while `fit_holds` (its frame still
  covers its slice) and fits again only those that do not. A wider margin is redrawn
  less often and is coarser: walking at a tenth of the box's diagonal a second and
  turning 15 degrees a second, the two maps are fitted again 8.2 and 1.3 times a second
  on Sponza's overview with no margin, 2.0 and 0.9 with 0.1, 0.9 and 0.2 with 0.25,
  while the edge error with the 2 x 2 filter grows 0.117, 0.129, 0.153 (at a close pose
  in italian_flat_97f97a20ba, 2.4 and 0.4, 1.6 and 0, 0.8 and 0 a second, the error
  0.163, 0.161, 0.159: there the fine map is finer than the frame needs).
- `shadow_traced.traced_sun`: the truth. Rays over the sun's disk (Blender's sun
  angle, 0.00918 rad), turned per pixel, against every triangle but transparent ones;
  masked holes pass. On a written plate and floor it is within 0.002 (mean) of the
  closed form.

Against the traced truth, the mean error in the pixels within 2 of an edge, side 2,048,
the DEPTH views' shifted planes in (host, 2026-11-27): italian_flat_97f97a20ba at a
close pose 0.247 with the 2 x 2 filter, 0.209 with a box of 5, 0.220 with PCSS, 0.165
with a cascade, 0.057 with a cascade and PCSS, 0.064 with its search on the levels;
breakfast_room's overview 0.180 with the 2 x 2 filter, 0.087 with PCSS; Sponza's
overview 0.200 with the 2 x 2 filter, 0.107 with a cascade and PCSS (either search). The texel reads a pixel:
4 for the 2 x 2 filter, 36 for a box of 5, 160 for PCSS of 32 taps (search and filter).
`checks/shadow_edge` checks these parts.

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
   `colour = tau C + (1 - max tau) a / pi E + S + F reflection R`. `E` is the glass's
   own irradiance by the rules of "Lighting" (sky x visibility, ambient, sun with
   shadow, lamps); `S` the `lit` kind's Blinn-Phong term for the sun and each lamp with
   the material's specular colour and exponent (always, when it has a specular colour);
   `R` the environment's radiance along `r = 2 (n.v) n - v` (the octahedral map's
   nearest texel, turned like the background); `F = F0 + (1 - F0)(1 - n.v)^5`,
   `F0 = 0.04`, `n.v` clamped at 0; `reflection` the scene's number of its `lighting`
   entry. Then the tone curve as for every pixel. With the term `glass_light` (off by
   default, until the card draws it):
   `colour = tau (1 - (F - F0)) C + (1 - max tau) a / pi E + S + F R'`, `F0` the
   material's specular colour, `R'` the radiance arriving along `r`: with `reflection`
   above 0, `reflection` x the environment's; else, with the term indirect, the field's
   irradiance at the glass for the normal `r` over pi (the room and the sky as the field
   holds them, a hemisphere's mean); else the sky's irradiance for `r` over pi. The
   converter's numbers make a BLEND material a coverage (its own diffuse and specular
   weighted by alpha, `tau = 1 - alpha` and its transmitted part) and a metal opaque
   ([glTF scenes](../../guides/gltf_scenes.md), "The mapping"). A thin surface: nothing
   is refracted, the surface behind is seen where it lies.
   `rasterize_shaded` (no lighting) uses
   `tau C + (1 - max tau) a light` with its light term and no `S` or `R`; on scenes without
   transparent materials its results are unchanged (no third FILL runs).
3. **Shadows.** Transparent triangles cast no shadow: the shadow map is
   `rasterize_shaded`'s 1/z, which is the surface behind the glass. With the term
   `glass_light` they take the sun's light by their materials' `shadow`: a glass map
   from the shadow map's camera (`sun_glass_map`: the 1/z of the glass nearest the sun
   and its material's `shadow`, the transparent triangles alone) multiplies the sun's
   irradiance by `shadow` at a point behind that glass (the four nearest texels,
   bilinear, the shadow's bias; one glass along the sun's way; the glass's own pixels
   are not attenuated). `shadow` is the materials file's, 1 for a file without it (the
   sun passes, as without the term): 0 for a refractive glTF surface, which then casts
   a full shadow, as Cycles reading the same file shows it (measured per glass object:
   the direct light behind refractive glass is 5 to 11 % of what it would be without
   it, the rest noise and indirect; under BLEND alpha 0.35 two panes pass 0.38 against
   0.65^2 = 0.42). The lamps have no visibility, so glass changes nothing of theirs: a
   lamp behind refractive glass lights through it, which Cycles does not, so a surface
   lit through glass by lamps or by the field (the sliding door's panel) stays brighter
   than Cycles' until lamps have visibility. The baked sky visibility is not rebuilt: it
   still treats glass as opaque.

   **Transmitted light (`transmit`).** A DEPTH view keeps its nearest opaque 1/z and,
   beside it, `T` (H, W, 3): the product over every glass fragment nearer than that 1/z
   (the glass layer drawn with FILL's coverage, order free, so no peeling) of the
   material's `transmission` tau times `(1 - F0)^2` (a pane's two faces at normal
   incidence, F0 0.04; the bend through a thin pane ignored). `transmittance(view,
   materials, opaque)` makes it for any view, `map_transmittance` for the sun's map in
   its quadrants, `lamp_maps.face_transmit` for a lamp's face; the lights carry the sun's
   as `shadow_transmit` (`with_map(..., transmit=True)`), and the sun's share
   (`sun_shares`) weights each of the four taps that is lit by its texel's `T` before
   the bilinear sum, per channel; with `shadow_transmit` the `glass_light` glass map is
   not made (it would count the glass twice). The lights keep `T` as the card does
   (`kept`, `map_kept`): 8 bits, each texel the mean of a `T_SCALE` x `T_SCALE` block of
   the map's texels (half resolution by default, a parameter of the map), one grey
   channel when every glass material's tau is grey and an RGB word (the fourth byte
   unused) when any is tinted, chosen once from the scene's materials (`t_channels`); a
   4 KiB page whose texels are all 255 is absent and reads 1, so a map keeps pages only
   where glass lies over its opaque surface. Against the full form (float, RGB, the map's
   resolution) the frame by this rule moved under 0.04 dB from Cycles on both scenes, and
   half resolution is 44.6 dB from the full form at most 27 codes apart (quarter: 39.9 dB,
   39). Why this rule: Cycles' direct passes show
   glass blocking because light that crossed glass is filed under its caustic paths,
   while its whole frame keeps that light; rendering Cycles with each glass material
   replaced by a rule (ignored, black, a straight pass of tau `(1 - F0)^2`) against its
   real glass, the third is within 2 to 3 % in the regions the glass changes (35 and 41
   dB on italian_flat and lynxsdesign at 640 x 360), the others 6 to 10 dB behind;
   blocking loses a quarter to a third of the light of italian's lamps in their glass
   bulbs. One `T` a texel is the product down to the nearest opaque surface, right for
   every point a texel lights (that surface): a surface between two panes is itself the
   nearest opaque, so a shelf between a bulb and a window takes the bulb's factor only.
   It is wrong for a point on a pane itself: a glass pixel's own light (its
   `(1 - max tau) a / pi E` and `S`) is given the product of its own pane and every pane
   behind it down to the opaque surface, too dark by them; it shows on a tinted or
   frosted pane lit through another (clear glass's own weight is near 0, so only its
   highlight), and the nearest glass's 1/z beside `T` would tell it. Glass lying on an
   opaque surface (a glass top on a table) is nearer or not by its float32 1/z against
   the surface's, as the fill orders two layers; `checks.glass_transmit` leaves such
   texels out of its traced comparison.
4. **Terms.** `glass` (default on): left out, transparent triangles are not drawn. `R`'s
   environment form needs `background`; `S` needs `specular` (without it the term
   `glass_light`'s `F0` is 0). `parts` gains the glass layer's own planes
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
(`native/raster/shade.hpp`) has no kind 5: it fills transparent triangles into its first layer as
an opaque surface ([raster](raster.md)). The card's texture stage has it (its glass form).

The sun camera's axes (right = y x forward, `direct.shadow.sun_camera`) stay as the shadow
maps were first made with them, not the view cameras' forward x y.

## The light pages a frame reads

`access` gives, per pixel of the padded frame, the pages LIGHT asks for, numbered as the
card numbers its light pages: one page space of 32 x 32 texels, the shadow map's pages
row by row, then the octahedral map's three channels, then the field's pages, from the
first pages LIGHT's table holds (the caller gives them as a layout, since the reference
does not read the card's headers).

- `light_surface`: the surface LIGHT lights, the masked layer where it is nearer and not
  a hole, else the opaque one, with each covered pixel's scene point and normal.
- `tap_texels`, `tap_pages`: a covered pixel's four taps (texels of the map, then their
  pages), the 2 x 2 filter of `shadow.sun_shadow` at the point moved one shadow texel
  along the normal; a tap outside the map reads none.
- `background_pages`: an empty pixel's (padding included) three channels of the
  background's octahedral texel, `sky.environment_radiance`'s texel.
- `field_cells`, `field_corner_voxels`, `field_corner_pages`: the lookup's cell and
  the eight voxels around the field's lookup point (`P + n h / 2`,
  as `indirect.field.values.lookup`), a page a block of voxels; a corner off the grid
  reads none. The field's pages are dense: a corner's page is asked whether or not its
  voxel holds data.
- `light_pages`: the three above over a frame, "shadow" (four pages a pixel, the
  background's in the first three) with "taps" (their texels), and "field" (eight)
  with "voxels" (their voxels) and "cells" (the lookup's cell).

`scripts/run/lookup_model.py` turns these, and `material.access`'s texture pages, into
the card's page passes and checks them against what the card counted; its record and
the check are in `measurements/lookup_model/`.
