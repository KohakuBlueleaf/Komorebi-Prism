# Near field of the indirect light

`prism_reference.indirect.near`: `screen` (the frame in the camera's axes, the coarse
copy), `measure` (a slice's cosine measure and its 32 bits), `march` (the near operator:
the samples of the two levels, their bits and sources), `fuse` (the rule's knobs, the
operator applied to a radiance image, the filter, the rule, the two bounces), `half` (the
same at half resolution and its upsample). Numpy only, no ray tracing. Its check:
`python -m checks.near_field` ([checks](../../guides/checks.md)).

## What it fixes

The field ([indirect](indirect.md)) misses the light bounced within about one element
spacing `h`: the transport clamps the form factor of near pairs and the field averages
over `2 h`. Lit by radiance 1 everywhere (the white furnace: every element's outgoing
light 1, the sky 1), the field's lookup reads `pi K` instead of `pi`, with `K` the share
of the hemisphere it keeps: 0.911 a pixel on the mean of Sponza's overview, 0.807 on
italian_flat's camera view, near 0 in creases. Contacts, the feet of walls and corners
stay too bright or too dark depending on what is near. The frame's own depth sees what is
near; the near field takes those directions from the frame and the rest from the field.

## The rule

At a pixel `x` with shading normal `n`, over the cosine measure
`d mu(w) = max(0, n.w) / pi dw` (the whole hemisphere has measure 1):

    E(x) / pi = sum over w in N(x) of L_s(y(w)) d mu(w)  +  (1 - mu(N(x))) Lfar(x)
    Lfar(x)   = E_far(x) / (pi K(x))

- `N(x)`: the directions in which the frame's depth shows a first hit `y(w)` closer than
  `R = 2 h` (the knob `near_range`).
- `L_s(y)`: the radiance the frame shows at `y`: its direct outgoing light (albedo / pi
  times the sun with its visibility and the lamps, or the emission) plus
  `albedo / pi E^(b-1)(y)`, the fused irradiance with one bounce fewer.
- `E_far`: the field's lookup at `b` bounces; `K`: the same lookup of the furnace's
  element irradiance (`E_el = M 1 + pi x` the element's escape share), over `pi`.
  `E_far / K` is a mean radiance over the hemisphere in which each direction counts by
  the share the field keeps of it.
- Where `K < 0.01` (`FLOOR_K`): `Lfar` is the near hits' mean radiance, or `E_far / pi`
  where nothing is hit.

Every direction gets one radiance: the frame's where it shows a near hit, the far mean
elsewhere. The near light is not counted twice (the field's partial copy of it is a weight
inside a normalised mean, not added light). Where the frame shows nothing (behind the first
layer, off the screen, past `R`) `mu(N) = 0` and the field stands alone, as `E_far / K`.
In the furnace (`L_s = 1`, `E_far = pi K`) `E / pi = mu(N) + (1 - mu(N)) = 1` at every
pixel whatever the frame shows, except where `K < 0.01` and nothing is hit, where it reads
`K`.

## The estimator

A visibility mask in the cosine measure. A pixel marches `slices` screen directions (4;
turned a pixel by a 4 x 4 pattern, with a jitter of the steps from the same pattern), two
sides each. In a slice, a direction is its angle `t` from the view vector, and the share of
`mu` the slice holds has the closed-form integral
`C(t) = -cos(2t - g) / 4 + t sin(g) / 2` over `[max(0, g - pi/2), min(pi, g + pi/2)]`, `g`
the angle of the normal projected into the slice. A side's 32 bits are 32 equal shares of
`C`: the measure of newly covered bits is their count times the share, with no weight a
bit.

A sample at a screen distance has a front point (its depth's point) and a back point
(`thickness` = `h / 2` behind it); its two angles map to a range of bits. Samples go from
near to far: bits not yet set take the sample's source. A sample is skipped when farther
than `R`, or when it does not rise above the receiver's plane by `0.05` of its distance
along the geometric normal (`plane`; a coplanar floor would bring its own light). A sample
whose surface faces away from the receiver brings only its indirect radiance
(`backface` 2, the default; 0 brings what the frame shows, 1 leaves its bits to the far
mean); `facing` 1 would weight its bits by its cosine toward the receiver (default 0).

The two levels:
- **short**: `short_steps` (8) at distances squared-spaced up to the halo, read at full
  resolution: within the pixel's 32 x 32 tile and a halo of `halo` (16) pixels around it;
- **long**: `long_steps` (8) from the halo to `reach_px` (512) pixels, read from one
  coarse copy of the whole frame at level `coarse_level` (3: 8 x 8 pixel cells) holding a
  cell's nearest pixel's point, its farthest depth and its mean radiance. A sample's slab
  goes from the nearest point to the farthest depth plus the thickness, capped at
  `coarse_cap` (one thickness) past the nearest: a cell is a depth interval.

The step counts are fixed: a step past `R` is idle. The operator is a list of entries
(pixel, source, weight, level); a source is a pixel, a coarse cell, or a pixel seen from
behind (its indirect radiance). The near radiance and the blocked share `mu(N)` are then
averaged over 5 x 5 pixels (`filter` 2) with weights from the depth (`exp(-(dz / 0.02 z)^2)`)
and the normals (`max(0, n.n')^8`), then fused. Two bounces: the first from the direct
outgoing light with the field at one bounce, the second from the direct light plus
`albedo / pi E1` with the field at two.

**Half resolution** (`half`): the receivers are every second pixel of every second row,
the focal length halved, the halo 8 half pixels, the coarse level 2 (the same 8 x 8 pixel
cells), reach 256 half pixels; the result is brought back by a 4-tap upsample weighted by
depth and normal. **Last frame's light**: the sources are the previous frame's radiance
reprojected through its depth (a source within 2 % of the depth it should have); a source
that fails brings no light and blocks nothing (its bits go to the far mean).

| knob (`fuse.RULE`, `march.SETTINGS`) | default | unit |
|---|---:|---|
| `near_range` | 2 | `h` |
| `thickness` | 0.5 | `h` |
| `coarse_cap` | 1 | thicknesses |
| `plane` | 0.05 | of the distance |
| `backface` | 2 | mode |
| `facing` | 0 | on or off |
| `filter` | 2 | pixels of radius |
| `slices`, `short_steps`, `long_steps` | 4, 8, 8 | |
| `halo`, `reach_px`, `coarse_level` | 16, 512, 3 | pixels, pixels, level |
| the cheap setting (half) | 2 slices, 8 + 8 steps, halo 8, level 2, reach 256 | half pixels |

## Against the truth

Host, 2026-11-27, 1,280 x 720 (the raster's 1,280 x 736, rows under 720), every second
pixel against `indirect.truth` (256 rays, two bounces: the field's count before it
followed the scene; [indirect](indirect.md) gives the field against the truth at the
scene's count); the sun at the elements and at the frame's pixels traced (italian_flat's file has no shadow map of its own). Scores on the
irradiance's luminance: ratio of the means / PSNR on `E / p99.5(truth)` clipped to 1 /
the same PSNR after the truth's 4 x 4 samples are averaged (8 x 8 pixels; the truth's own
noise dominates the first PSNR). Pixels where the truth reads 0 are left out (a Sponza
floor triangle and masked leaves that the truth misses, 2.5 %; italian_flat's television).
"128" is the full setting (128 samples a pixel), "half" the cheap one (64 a half pixel, 16
a full pixel).

| view | the field alone | fused, 128 | fused, half |
|---|---|---|---|
| Sponza overview | 0.915 / 19.37 / 20.93 | 0.949 / 21.44 / 23.66 | 0.955 / 21.32 / 23.57 |
| Sponza close (eye -515.9, 587.6, -156.6, target -277, 515, -254, 60 degrees) | 1.018 / 16.32 / 18.90 | 0.979 / 19.29 / 22.26 | 0.982 / 19.22 / 22.19 |
| italian_flat, its camera | 0.838 / 20.86 / 24.71 | 0.902 / 21.61 / 26.89 | 0.915 / 21.56 / 26.83 |
| italian_flat close (eye 3.759, 1.083, -10.062, target 4.0, 0.08, -8.1, 60 degrees) | 0.887 / 21.36 / 24.42 | 0.889 / 22.18 / 26.22 | 0.893 / 22.17 / 26.21 |
| lynxsdesign_a01894bbb8, its camera | 0.838 / 16.72 / 18.45 | 0.927 / 18.92 / 21.84 | 0.931 / 19.00 / 22.00 |

The furnace reads 1.0000 (min, mean and max) at every pixel of all five views with the
filter on. Without the filter it fails at pixels with `K < 0.01` and no hit (they read
`K`); the filter gives them their neighbours' hits. The raster draws nothing below about
row 530 at italian_flat's close view: its numbers are over the covered part.

On the half setting, fewer steps cost more than fewer slices or half resolution: at 4 + 4
or 2 + 2 steps at full resolution Sponza close loses 0.7 to 1.6 dB; half resolution with
8 + 8 steps is within 0.12 dB of 128 on all five views. With last frame's light (the
previous camera one walking step back, 0.1 of the scene's diagonal a second at 30 frames
a second, and five times that), the result stays within 0.1 dB of this frame's light, except
on italian_flat's close view (-0.8 dB), where the previous frame's raster cut lies in
other rows. A camera whose previous frame saw nothing of this one (stepping back through a
wall) leaves the field alone, with `K`.

The screen's near share against a traced one (the share of each pixel's cosine rays that
hit within `R`): 0.134 against 0.163 on Sponza's overview, 0.158 against 0.231 on
italian_flat's camera view, 0.260 against 0.362 on its close view. The rest is behind the
first layer or off the screen.

## The artefacts and what causes each

Each cause is shown by one changed run.

- **Light at silhouettes** (yellow at the plinths' corners, blue on the balustrade, Sponza's
  overview): samples of surfaces that do not face the receiver. It stays with the long
  steps at full resolution, so it is not the coarse cells' mixing; it mostly goes with
  `backface` 2, the default (a yellow strip stays at a plinth's foot). `facing` 1 removes
  it too but also removes true near occlusion (`mu(N)` 0.137 to 0.081 on Sponza close; -0.7 to -0.9 dB).
- **A coloured band on a pedestal's side** (Sponza close): the long level's slab
  thickness covering directions behind an edge. It goes with a thickness of `h / 4` or
  without long steps (-0.8 dB on the whole at `h / 4`); it stays with every other knob.
- **No shadow under a seat** (italian_flat close): the seat's underside is behind the first
  layer the camera sees. No near range (2, 4, 8 `h`) brings it.
- **A warm wall behind shelves** (italian_flat's camera view): the field's, present in the
  field alone; the thickness moves the whole shelf, not the patch.
- **Diagonal streaks over a sofa** (lynxsdesign_a01894bbb8): its normal map. They stay
  without the filter, with 8 slices and a wider filter; they go with the geometric normal
  as the receiver's lobe.
- **A dither on columns** at one slice a pixel (half, 8 samples a full pixel): the 4 x 4
  pattern of slice directions shows.
- **Brightening beside near surfaces** when `E_far / K` alone is used without the frame
  (the field compensated): it fixes the mean (ratios 0.99 to 1.04) but brings the far mean
  into directions a near surface blocks; fused, the contacts darken as the truth does.

## The form a tile could run

Options of the reference that bound what one 16 x 16 tile of half pixels reads, each off
by default:

- **`angles`** (`march.SETTINGS`): `"exact"` (atan2 and the closed form, the default) or
  `"free"` (`measure.side_share_free`: the angle by an odd polynomial of degree 13 with an
  octant reduction, largest error 2.5e-7, and `cos(2t - g)` from the sample's coordinates
  by the angle sum; no trigonometric call).
- **`tile`** (`march.SETTINGS`, the rows marched together and the tile of the receiver);
  `fuse.smooth(.., tile)` and `half.upsample(.., tile)` take no pixel of another tile.
- **Last frame's geometry**: `frame["previous"] = fuse.previous_frame(camera, last)`;
  short samples outside the receiver's tile and every coarse sample are read from the last
  frame's depth at the receiver's place in it, their points turned into the current
  camera (levels 2 and 3 of the entries); `fuse.near_radiance(.., previous)` takes those
  entries' sources from the last frame's radiance.
- **One apply a frame**: `fuse.one_apply`, one near bounce from the direct light plus
  `albedo / pi` times the last frame's E, fused with the field; repeated a frame, it
  replaces the two bounces.

The furnace reads 1 at every pixel with all four on. Scores as above (same views,
half setting with 2 slices); "walk" is the previous camera one walking step back, "fast"
five times that; "one apply" is 8 frames from the field alone on a still camera; "all" is
the tile, last frame's geometry, its coarse copy and one apply together (the previous view
converged over 8 frames). The coarse copy's cells are given in full-resolution pixels.
Contact crops (x0, y0, x1, y1): Sponza overview 150, 250, 400, 340; Sponza close 416, 330,
832, 470; italian_flat camera 280, 520, 640, 720; italian_flat close 520, 80, 820, 240;
lynxsdesign 0, 470, 400, 660.

Whole frame:

| view | half | cells 16 px | cells 32 px | tile | one apply | light only, walk | geometry, walk | geometry, fast | all, walk |
|---|---|---|---|---|---|---|---|---|---|
| Sponza overview | .955 / 21.32 / 23.57 | .943 / 21.16 / 23.37 | .934 / 20.76 / 22.76 | .955 / 21.31 / 23.55 | .958 / 21.33 / 23.58 | .961 / 21.39 / 23.71 | .962 / 21.49 / 23.85 | .967 / 21.46 / 23.77 | .965 / 21.50 / 23.85 |
| Sponza close | .982 / 19.21 / 22.18 | .965 / 18.83 / 21.75 | .941 / 18.07 / 20.69 | .982 / 19.21 / 22.18 | .985 / 19.21 / 22.19 | .984 / 19.19 / 22.15 | .979 / 19.22 / 22.17 | .970 / 19.39 / 22.40 | .981 / 19.22 / 22.21 |
| italian_flat camera | .915 / 21.56 / 26.83 | .910 / 21.50 / 26.79 | .922 / 21.52 / 26.73 | .915 / 21.55 / 26.85 | .931 / 21.55 / 26.78 | .928 / 21.52 / 26.76 | .928 / 21.57 / 26.93 | .939 / 21.53 / 26.87 | .942 / 21.55 / 26.89 |
| italian_flat close | .893 / 22.17 / 26.21 | .874 / 22.04 / 25.88 | .860 / 21.82 / 25.41 | .893 / 22.16 / 26.20 | .908 / 22.07 / 26.04 | .922 / 21.38 / 24.77 | .883 / 22.19 / 26.37 | .890 / 22.17 / 26.34 | .895 / 22.18 / 26.36 |
| lynxsdesign | .931 / 19.00 / 22.00 | .927 / 18.87 / 21.81 | .929 / 18.84 / 21.77 | .931 / 18.98 / 21.98 | .956 / 19.22 / 22.46 | .934 / 19.02 / 22.05 | .932 / 18.96 / 21.96 | .940 / 18.96 / 21.97 | .956 / 19.18 / 22.41 |

Contact crops:

| view | half | cells 16 px | cells 32 px | tile | one apply | light only, walk | geometry, walk | geometry, fast | all, walk |
|---|---|---|---|---|---|---|---|---|---|
| Sponza overview | .987 / 26.21 / 29.56 | .960 / 26.10 / 29.14 | .968 / 25.39 / 28.12 | .987 / 26.23 / 29.62 | .990 / 26.20 / 29.55 | .988 / 26.20 / 29.57 | .985 / 26.17 / 29.53 | .989 / 26.09 / 29.45 | .987 / 26.19 / 29.57 |
| Sponza close | .894 / 16.79 / 18.40 | .865 / 16.42 / 17.97 | .819 / 15.41 / 16.80 | .894 / 16.79 / 18.40 | .898 / 16.81 / 18.44 | .896 / 16.76 / 18.41 | .894 / 16.80 / 18.49 | .891 / 16.89 / 18.50 | .897 / 16.82 / 18.53 |
| italian_flat camera | .886 / 31.56 / 37.44 | .851 / 31.29 / 36.50 | .859 / 30.93 / 35.47 | .886 / 31.56 / 37.44 | .902 / 31.59 / 37.54 | .887 / 31.56 / 37.44 | .883 / 31.58 / 37.50 | .979 / 30.70 / 34.99 | .899 / 31.61 / 37.63 |
| italian_flat close | .982 / 20.91 / 24.23 | .968 / 20.84 / 24.09 | .961 / 20.66 / 23.75 | .982 / 20.90 / 24.22 | .989 / 20.90 / 24.22 | .982 / 20.91 / 24.23 | .983 / 20.91 / 24.24 | .980 / 20.97 / 24.38 | .989 / 20.90 / 24.23 |
| lynxsdesign | .988 / 18.79 / 21.58 | .972 / 18.35 / 20.92 | .979 / 18.15 / 20.62 | .988 / 18.78 / 21.56 | 1.066 / 18.56 / 21.21 | .997 / 18.85 / 21.71 | .989 / 18.79 / 21.67 | 1.013 / 18.68 / 21.50 | 1.065 / 18.49 / 21.15 |

- `"free"` angles give the same operator to rounding: the blocked share differs at 15 of
  235,520 half pixels (Sponza overview; largest 0.005) and 9 of 170,880 (italian_flat
  close; 0.019), E by at most 0.07 %; the scores above are identical to 4 decimals.
- Last frame's geometry outside the tile is never worse than last frame's light on the
  current geometry, and removes its loss on italian_flat's close view (b8 24.77 to 26.37).
  Of the entries' weight, 5 to 11 % is read from the last frame's pixels, 46 to 68 % from
  its coarse copy.
- 16 px cells cost 0.1 to 0.9 dB, 32 px up to 2.0 dB on Sponza close's contact crop.
- The tile-bounded filter and upsample change the scores by under 0.03 dB; the difference
  lies on the tile lines (mean 0.7 % of E, 99th percentile 8 to 12 %).
- One apply a frame converges on a still camera: E changes 13 to 18 % in the first frame,
  0.4 to 1.0 % in the second, 0.03 to 0.16 % in the third, nothing after the fifth. The
  ratio rises 0.3 to 2.5 points against two bounces; on lynxsdesign's contact crop it
  passes the truth (0.988 to 1.066).

### One step compiled

One march step of one vector of 32 samples (screen position, pixel index, two indexed
loads of depth and packed normal, front and back points, distance, the plane and range
tests, two dots and a share for each point, the bits, a popcount, the weight, the
back-face test), written for the pack processor as the direct light's kernels are
(vector-unit instruction macros, RVV indexed loads; `stages/direct/light`), compiled with
the runtime's flags for that processor (`riscv-tt-elf-g++ -O3 -mcpu=tt-bh-tensix`, the
`zve32f` vector extension), counted on the disassembly as issued vector-unit
instructions (stores to the instruction buffer and direct vector instructions):

| step | vector instructions | text bytes |
|---|---:|---:|
| exact, own tile | 509 | 3,600 |
| free, own tile | 465 | 3,400 |
| exact, last frame's sample (both points turned) | 567 | 3,996 |
| free, last frame's sample | 523 | 3,800 |

Every macro with operands compiles to three scalar instructions (12 bytes). The cycles an
instruction come from the direct light's row compiled the same way with Sponza's terms
(shadow, specular, no lamps): its measured laps, 644 and 1,107 cycles a vector of 32
pixels, over 230 and 291 issued instructions, give 2.80 and 3.80 cycles an instruction
(3.36 over both); an indexed load of 32 lanes takes about 152 cycles. At 1,920 x 1,080,
half resolution, 64 samples a half pixel (26 short own, 6 short from the last frame,
32 coarse with three loads), 120 cores at 1.35 GHz:

| cycles an instruction | exact | free |
|---:|---:|---:|
| 2.80 | 12.2 ms | 11.4 ms |
| 3.36 | 14.1 ms | 13.2 ms |
| 3.80 | 15.6 ms | 14.6 ms |

The free angles save 44 of 509 instructions: they keep the arctangent and drop the cosine
and its range reduction.

## One tile

`near/one_tile.py` writes both fields of a 32 x 32 px screen tile as one product,
`E = W_T . S_T`: `W_T` has a row a half pixel (256 a tile) and 32 columns, `S_T` is 32
colours a tile. The product's E is upsampled to full pixels after it (`half.upsample`
within the tile). The form:

- **Near columns (20)**: the tile (16 x 16 half pixels) in 2 x 2 cells of 8, then two
  rings of 8 cells around it, of 16 and 48 half pixels (`tile.PATTERN`). The march's
  entries are credited to the cell their sample lies in (`tile.near_weights`); a sample
  outside the pattern sets no bits, its directions go to the far field. Seen-from-behind
  samples count as the cell's front (back face 0). The tile-bounded filter is applied to
  `W` itself. `S_near` is each cell's mean radiance over its covered half pixels
  (`tile.cell_values`, by summed tables).
- **Far columns (12)**: the field lookup written as weights on its 24 (voxel x 6 +
  direction) entries a pixel (`tile_far.lookup_weights`, equal to `values.lookup`). A
  tile reads a median 60 to 96 distinct entries, at most 250 to 950. They are put into
  12 groups (`tile_far.grouped`): the six directions share the groups by the weight they
  carry, and a direction's entries are split in halves along their box's longest side
  at the weighted share. `W_far[pixel, g]` is the sum of the pixel's weights in group
  `g`: nonnegative, each row's sum kept. `S_far[g]` is the group's field values averaged
  with the tile's column sums as weights. A tile with 12 entries or fewer keeps them as
  they are.
- **The fusion as weights** (`tile_far.tile_weights`): `pi W_near` and
  `(1 - blocked) / K W_far`, with `K` the grouped lookup of the furnace's field over pi;
  where `K` is under `FLOOR_K`, `W_near / blocked` with hits and `W_far` alone without.
  The ambient term where no lookup finds the field stays outside the product. The
  furnace reads 1 by construction (`checks.near_field`).

What is recomputed when: `W_T` depends on the geometry and the eye only (a moved sun
gives the same `W_T` to the bit; the check holds `W_T` and compares it against one
rebuilt under the moved sun). It is rebuilt when the eye or the geometry moves.
`S_near` is rebuilt every frame from the lit radiance. `S_far` is rebuilt when the field
changes, or when the groups change with `W_T`.

On the five views (two bounces, h16 setting; ratio / PSNR / PSNR in 8 bits; the second
group's scores take `W_T` in bfp8_b and `S_T` in bfloat16; "p99" is that 8-bit error's
99th percentile in units of the frame's mean E; "lookup" is the far columns' mean error
against the full lookup of the field):

| view | rows | far basis | whole | contact | whole, 8 bit | contact, 8 bit | p99 | lookup |
|---|---|---|---|---|---|---|---:|---:|
| Sponza overview | full | SVD | .966 / 21.01 / 23.44 | .988 / 26.16 / 29.68 | 23.44 | 29.64 | 5.6 % | 1.5 % |
| Sponza overview | half | SVD | .966 / 21.01 / 23.43 | .988 / 26.18 / 29.69 | 23.43 | 29.68 | 4.7 % | 1.4 % |
| Sponza overview | half | groups | .966 / 20.95 / 23.33 | .993 / 26.19 / 29.75 | 23.33 | 29.75 | 1.3 % | 3.8 % |
| Sponza close | full | SVD | .998 / 19.25 / 22.29 | .925 / 17.21 / 19.16 | 22.29 | 19.15 | 4.1 % | 0.3 % |
| Sponza close | half | SVD | .998 / 19.25 / 22.29 | .925 / 17.21 / 19.16 | 22.30 | 19.17 | 3.7 % | 0.3 % |
| Sponza close | half | groups | .999 / 19.22 / 22.26 | .925 / 17.24 / 19.19 | 22.25 | 19.18 | 1.4 % | 1.6 % |
| italian_flat camera | full | SVD | .928 / 21.40 / 26.85 | .893 / 31.57 / 37.53 | 26.84 | 37.53 | 10.0 % | 2.1 % |
| italian_flat camera | half | SVD | .928 / 21.42 / 26.86 | .893 / 31.57 / 37.53 | 26.86 | 37.52 | 8.9 % | 1.9 % |
| italian_flat camera | half | groups | .928 / 21.36 / 26.70 | .896 / 31.54 / 37.49 | 26.70 | 37.48 | 2.1 % | 4.1 % |
| italian_flat close | full | SVD | .897 / 22.17 / 26.25 | .985 / 20.91 / 24.23 | 26.25 | 24.23 | 5.8 % | 0.4 % |
| italian_flat close | half | SVD | .897 / 22.18 / 26.26 | .985 / 20.91 / 24.24 | 26.26 | 24.22 | 4.8 % | 0.4 % |
| italian_flat close | half | groups | .899 / 22.14 / 26.19 | .985 / 20.95 / 24.33 | 26.18 | 24.33 | 3.8 % | 2.4 % |
| lynxsdesign | full | SVD | .934 / 18.94 / 22.03 | .991 / 18.76 / 21.56 | 22.07 | 21.57 | 5.2 % | 1.7 % |
| lynxsdesign | half | SVD | .934 / 18.95 / 22.03 | .991 / 18.75 / 21.56 | 22.07 | 21.57 | 4.3 % | 1.6 % |
| lynxsdesign | half | groups | .934 / 18.95 / 21.98 | .994 / 18.63 / 21.41 | 21.98 | 21.40 | 1.1 % | 3.8 % |

- Half rows against full rows: within 0.02 dB on every view and crop. `W_T` at half rows
  is 8,704 bytes a tile in bfp8_b (full rows 34,816).
- Groups against the SVD basis (`tile_far.basis`, signed, exact on the furnace by
  deflation): the lookup's error rises from 0.3 to 1.9 % to 1.6 to 4.1 % and the scores
  fall by 0.03 to 0.16 dB; the 8-bit error's p99 falls from 3.7 to 8.9 % to 1.1 to 3.8 %
  and its largest value by up to 3 times. The groups are the form: nonnegative columns
  that keep the 8-bit error under the format's step, and `S_far` a weighted average the
  card computes without a factorization.
- `W_T` for a view at 1,920 x 1,080 takes 2.3 s on one host core after the march (6.7 s).

The one-tile form does not replace any block of the transport. Of the dense cluster
pairs of Sponza's transport, 1.9 % lie within the screen term's reach (centres within
2 h); a transport built without its near blocks loses its multiple bounce (K 0.91 to
0.16 on Sponza, 0.81 to 0.11 on italian_flat). The far field keeps all its blocks. What
the one-tile form gives is the detail below an element's size, and the field's
per-pixel lookup turned into a product.
