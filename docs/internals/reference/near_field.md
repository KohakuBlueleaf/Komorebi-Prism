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
pixel against `indirect.truth` (256 rays, two bounces); the sun at the elements and at the
frame's pixels traced (italian_flat's file has no shadow map of its own). Scores on the
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
