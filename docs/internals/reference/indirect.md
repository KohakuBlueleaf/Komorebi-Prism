# Indirect light

`prism_reference.indirect`: `elements` (sampling, the probe, padding), `form_factors`
(rows of F and the dense build), `hmatrix/` (`cluster`: the cluster tree and the
partition; `compress`: the blocks; `apply`; `card`: the card's numbers emulated), `sky`
(25 harmonics, the transfer rows), `field/` (`build`, `values` and the lookup, `pack`),
`light` (the element light, the field's source, the pixel's irradiance), `files`, `build`
and `truth`. The rays are traced by `trace.batch` ([trace](trace.md)).


The optional term `indirect` of `rasterize_lighted` (`terms=direct.frame.TERMS +
("indirect",)`; left out by default, so every lit frame without it is unchanged, bit for bit)
replaces `ambient` and `sky x visibility` by the light bounced between surfaces and the
sky with its visibility, from precomputed data. Defined in `prism_reference.indirect`, numpy
with one native routine: `native/trace/trace_batch.cpp` traces many rays at once with the
reference tree walk and triangle test (`native/trace/raytrace_core.hpp`), threaded (at most 8 or
`PRISM_THREADS`), built by `native.build` as a shared library. Its rays see glass as open (a
tree over the triangles that are not `transparent`); masked triangles are opaque.

```bash
python scripts/data/public_scenes.py indirect sponza      # <scene>_indirect.npz and <scene>_transport/
```

1. **Elements.** `elements` points (the `lighting` entry's, default 50,000) sampled by
   area: element k at area `(k + 0.5) A / N` of the cumulative triangle area (glass has
   none), uniform in its triangle from the hash of k (seed 31); each has the triangle's
   normal (its winding), area `A / N`, the triangle's colour (albedo texture at the
   centroid's coordinates in the 16 x 16 level, times the base colour) as albedo, or, for
   `emissive` materials, as emission (albedo 0). Dropped: those whose 32 cosine rays
   (seed 41) from `p + eps n` escape or hit within 10 eps in more than 97 % (they see
   only the void, or are buried), and those whose form-factor row is empty. The kept
   count is padded to a multiple of 32 with zero-area copies and ordered by a cluster
   tree of whole 32-element units (a node of u units cuts its box's longest axis at
   `u // 2` units; leaves of at most 256 elements).
2. **Transport.** `F_ij = V max(0, cos_i) max(0, cos_j) A_j / (pi r^2 + A_j)` (the near
   field clamped as a disc of area `A_j` seen on its axis), `V` one any-hit ray between
   the points moved `eps` along their normals, 0 on the diagonal; built dense once
   (kept in `<scene>_indirect_work/`, from which a stopped build goes on), then stored as
   a hierarchical matrix of `M = pi F`: admissible when the boxes' separation (gap over
   the larger diagonal) is at least 1, zero blocks dropped, low rank where the rank at
   1e-2 of the block's largest singular value stores fewer numbers than the block. The
   files are the card's (the stage `indirect.transport` reads them): `<scene>_transport/` with `blocks.npz`,
   `weights.f32`, `x`, `y_exact`, `y_float`, `y_q8`, `perm.npy` and a README of the
   layout. The reference's apply is that hierarchical matrix in float32 (`indirect.hmatrix.apply`,
   the README's loop): `E = M L`.
3. **The sources.** For the current lights each element's outgoing light is
   `L0 = emission x emissive_scale + albedo / pi (sun + lamps + sky)`: the sun with the
   shadow map's lookup as a pixel has it, the lamps without shadows, the sky of item 4.
   The bounce passes: `E1 = M L0`, `E_k = M (albedo / pi E_(k-1))`, `E = E1 + ... +
   E_b`, b = `lights["bounces"]` (the `lighting` entry's `bounces`, default 2; 0 or more,
   anything else refused). With 0 the field holds only each element's own sky
   irradiance: a frame is direct light only (the sun, the lamps, the sky with its
   visibility). With the default every frame is the earlier one bit for bit.
4. **The sky** by 25 spherical harmonics (bands 0 to 4): each element has a transfer row
   `T_k = pi / 256 sum Y_k(w)` over those of 256 cosine rays (seed 51) from `p + eps n`
   that escape; its sky irradiance is `max(0, T c)`, `c` (25 x 3) the least-squares fit,
   weighted by solid angle, of the basis to the turned octahedral map with its sun's cone
   replaced by the 4 to 8 degree ring's mean (as the 9 coefficients have it), on a
   256 x 512 grid. A turn of the sky changes `c` only. Another form, 32 patches of
   equal solid angle over the upper hemisphere (4 bands x 8 sectors), was measured first
   and did worse (table below): it is not used.
5. **The field.** Voxels of side `h` = the element spacing `sqrt(A / N)`, six directions
   (+-x, +-y, +-z). (voxel, d) = `sum w E / sum w` over the elements within `R = 1.5 h` of
   its centre, `w = max(0, n.d) (1 - (r/R)^2)^2`, a fixed sparse matrix from the elements
   to the (voxel, d) values. A (voxel, d) with no element takes the row of the nearest
   voxel (centre distance at most 2 voxels; ties by offset order) whose d has one, else
   none. What it holds: `E` of item 3 plus the element's own sky irradiance.
6. **A pixel.** With `indirect`, `E = I(P, n) + sun x max(0, n.s) x shadow + lamps`:
   `ambient` and `sky x visibility` are dropped. `I`: at `Q = P + n h / 2` the 8 voxel
   centres around Q with trilinear weights; per axis the direction of `n`'s sign over the
   voxels with data, weights renormalised; `I = sum n_a^2 V_a` over the axes that found
   data, over the sum of their `n_a^2`. Where no voxel has data the pixel takes
   `ambient`. Glass's own `E` uses the same lookup. `parts` gains `indirect`
   (`a / pi I`); `sky` is 0.
7. **Lights.** `direct.lights.load` gives the path of `<scene>_indirect.npz` as
   `lights["indirect"]` when the file exists; without it the term is refused with a
   message naming the command. After `direct.lights.moved` the sources and the field's values
   are recomputed (item 3) on the next frame; no file is rebuilt. `lights["bounces"]`
   (`load`: the entry's, default 2) may be overridden in the dictionary; a new count
   remakes the field's values the same way.

The count (host, one process on 8 CPUs, 2026-11-24 02:53 to 02:56): the field's values
for the lights (the light stage's `model/field.py` `field_of`: sources, the passes, the field's
weights, packing; best of 3) and the mean of the frame's `indirect` part (luminance, `a /
pi I`, over the visible pixels of the view's own camera at 1,024 x 1,024):

| bounces | Sponza overview: field s, mean | Bistro interior overview: field s, mean |
|---:|---|---|
| 0 | 0.164, 0.00611 | 0.147, 0.00085 |
| 1 | 0.624, 0.01188 | 0.918, 0.00736 |
| 2 | 1.127, 0.01324 | 1.689, 0.00820 |
| 3 | 1.607, 0.01348 | 2.448, 0.00831 |

Each pass adds one apply of the transport (0.48 s Sponza, 0.77 s Bistro interior). The
first pass adds 0.94 times the sky's part on Sponza and 7.6 times on the Bistro
interior (lit through its windows and by its lamps); the second 0.24 and 0.13 of the
first's, the third 0.18 and 0.13 of the second's (1.8 % and 1.3 % of the total).

`indirect.truth.truth` (not part of `rasterize_lighted`) gathers the truth per pixel: 256
cosine rays about the pixel's normal from its point moved `eps` along the triangle's
normal; an escape adds the sky (the same map, sun removed), a hit its sun (shadow ray),
lamps and emission, then one cosine ray from it adds the sky times its albedo (the first
bounce of every source), its hit's direct light times the albedo, and one more ray the
sky times both albedos (the second bounce).

What it gets wrong: the light bounced within
one element spacing is missed: walls next to sunlit ledges and sills, column bases,
arcade back walls and the curtains' lower edges next to the sunlit floor stay dark (blue
in the ratio pictures); the field's average over 1.5 spacings mixes the elements of a
curved surface that face the sky or the sun with those that do not, so arch soffits,
vault strips and capitals are too bright (red); the open floor sees only
the zenith, which 25 coefficients still underestimate (its sky -14 % on the elements).
The frame is about 20 % dark on Sponza. The element sources use the shadow map and the
truth shadow rays.

Built on the host, 8 threads on 8 CPUs, 2026-11-23 22:00 to 22:26 (`counts` in the
file; Bistro's F in two runs of 575 and 101 s, the first stopped by a time limit):

| | Sponza | Bistro interior |
|---|---:|---:|
| sampled / probe dropped / empty rows / kept / N | 50,000 / 10,800 / 2,382 / 36,818 / 36,832 | 50,000 / 6,341 / 1,444 / 42,215 / 42,240 |
| element spacing = voxel side, eps | 50.3, 0.093 | 14.8, 0.049 |
| F with visibility | 334 s, 554.8 M rays | 676 s, about 927 M rays |
| drop, tree, order / hierarchical / transfer / field / checks | 12.9 / 140 / 2.0 / 0.8 / 9.2 s | 16.6 / 276 / 7.9 / 1.0 / 15.5 s |
| blocks: low rank / dense near / admissible dense | 8,406 / 13,024 / 0 | 11,878 / 13,608 / 68 |
| median rank | 14 | 29 |
| tiles (dense / low rank) | 421,426 (265,798 / 155,628) | 774,298 (364,386 / 409,912) |
| `weights.f32`, `<scene>_indirect.npz` | 1,726 MB, 26.4 MB | 3,172 MB, 34.4 MB |
| voxels; directions with elements / filled; weights | 72,367; 184,634 / 110,541; 1.08 M | 83,089; 269,965 / 127,342; 1.50 M |
| float32 apply vs dense: median / p99 / sum ratio | 1.4e-4 / 1.7e-2 / 0.99997 | 1.7e-4 / 1.0e-2 / 1.00000 |
| card numbers emulated (`y_q8`) vs dense | 1.45e-3 / 4.0e-2 / 0.9998 | 8.2e-4 / 3.2e-2 / 0.9997 |
| sources, two applies and field per lights | 1.7 s | 2.5 s |

(element errors over the elements whose exact luminance is above 1e-4.) The sky rules
against gathering the map along the same 256 rays an element (50,000 sampled, the live
ones; luminance; median / p90 / sum ratio over those seeing sky):

| | 32 patches | 9 harmonics | 25 harmonics |
|---|---|---|---|
| Sponza, all seeing sky (6,057) | 0.10 / 0.69 / 1.22 | 0.09 / 0.32 / 1.01 | 0.05 / 0.23 / 1.00 |
| Sponza, open floor (281) | 0.24 / 0.37 / 0.76 | 0.26 / 0.42 / 0.74 | 0.17 / 0.30 / 0.86 |
| Sponza, open floor, sun moved 90 degrees | 0.22 / 0.36 / 0.76 | 0.19 / 0.33 / 0.80 | 0.09 / 0.22 / 0.93 |
| Bistro interior, all seeing sky (26,113) | 0.47 / 2.47 / 1.36 | 0.15 / 0.46 / 1.03 | 0.14 / 0.64 / 1.00 |

The patches count a ray escaping below the horizon in the horizon band; 37 % of the
Bistro's escaping rays go down (its windows), which the upper hemisphere cannot hold
(dropping them: 0.27 / 1.00 / 0.84).

Against the truth (512 x 512, every second pixel of the 1,024 frame, visible and not
emissive; the Bistro's 1,369 pixels with glass in front left out), irradiance
luminance: median / p90 of the relative error over pixels whose truth is above 0.01,
mean |error| over mean truth, ratio of the means; "blurred": both over 5 x 5 pixels
(most of the truth's own noise gone); "today": `ambient + sky x visibility`.
Kinds of place: open floor (n_y > 0.9, y -30 to 10, the truth's escape
share > 0.05), sunlit walls (|n_y| < 0.2, sun part > 1e-4), under the arcades (y -50 to
350, not sunlit, escape < 0.03), the upper gallery (y 350 to 1,000, not sunlit, escape
< 0.1).

| view, place | pixels | indirect | indirect, blurred | today |
|---|---:|---|---|---|
| Sponza overview, all | 258,059 | 0.26 / 0.72 / 0.32 / 0.81 | 0.22 / 0.59 / 0.26 / 0.81 | 0.74 / 7.16 / 0.81 / 1.63 |
| open floor | 30,516 | 0.20 / 0.43 / 0.24 / 0.80 | 0.17 / 0.36 / 0.20 / 0.81 | 0.22 / 0.81 / 0.27 / 1.18 |
| sunlit walls | 50,106 | 0.26 / 0.72 / 0.32 / 0.76 | 0.22 / 0.65 / 0.28 / 0.76 | 0.93 / 2.37 / 0.73 / 1.32 |
| under the arcades | 37,044 | 0.23 / 0.76 / 0.29 / 0.94 | 0.15 / 0.54 / 0.18 / 0.93 | 0.62 / 7.66 / 0.94 / 1.81 |
| upper gallery | 111,682 | 0.29 / 0.83 / 0.36 / 0.84 | 0.25 / 0.63 / 0.29 / 0.84 | 1.40 / 11.68 / 1.31 / 2.28 |
| Sponza close, all | 261,494 | 0.25 / 0.63 / 0.32 / 0.78 | 0.21 / 0.53 / 0.27 / 0.78 | 0.47 / 5.20 / 0.59 / 1.19 |
| open floor | 65,405 | 0.19 / 0.40 / 0.23 / 0.81 | 0.18 / 0.30 / 0.19 / 0.82 | 0.20 / 0.66 / 0.24 / 1.14 |
| sunlit walls | 47,446 | 0.23 / 0.47 / 0.28 / 0.76 | 0.21 / 0.44 / 0.26 / 0.76 | 0.50 / 1.10 / 0.51 / 0.78 |
| under the arcades | 64,392 | 0.36 / 0.81 / 0.45 / 0.69 | 0.29 / 0.69 / 0.37 / 0.70 | 0.59 / 12.12 / 0.79 / 1.17 |
| upper gallery | 64,797 | 0.31 / 0.82 / 0.36 / 0.85 | 0.25 / 0.61 / 0.28 / 0.85 | 1.10 / 12.37 / 1.18 / 2.07 |
| Sponza overview, sun +90 degrees, all | 258,059 | 0.25 / 0.67 / 0.31 / 0.81 | 0.20 / 0.55 / 0.25 / 0.81 | 0.75 / 7.57 / 0.85 / 1.64 |
| open floor | 30,516 | 0.17 / 0.41 / 0.21 / 0.85 | 0.10 / 0.34 / 0.15 / 0.86 | 0.26 / 0.71 / 0.28 / 1.23 |
| sunlit walls | 46,347 | 0.22 / 0.58 / 0.29 / 0.80 | 0.20 / 0.52 / 0.25 / 0.80 | 0.64 / 2.46 / 0.64 / 1.11 |
| under the arcades | 31,754 | 0.28 / 0.74 / 0.37 / 0.88 | 0.20 / 0.58 / 0.26 / 0.86 | 1.41 / 11.61 / 1.59 / 2.49 |
| upper gallery | 123,893 | 0.27 / 0.73 / 0.34 / 0.84 | 0.22 / 0.56 / 0.28 / 0.83 | 1.30 / 10.59 / 1.30 / 2.28 |
| Bistro interior overview, all | 245,550 | 0.13 / 0.39 / 0.17 / 0.94 | 0.07 / 0.26 / 0.11 / 0.94 | 0.89 / 0.95 / 0.85 / 0.18 |

Pixels with no voxel data (fallback to `ambient`): 11, 13, 11 and 1. A frame with
`indirect` took 8.1 to 8.7 s on Sponza against 5.4 to 5.5 s without (numpy, 8 CPUs;
the first one of a lights also 1.7 s for the sources and the field), 12.8 against
10.4 s on the Bistro interior. The truth took 124 to 129 s a Sponza view (5 rays a
sample) and 266 s on the Bistro interior.
