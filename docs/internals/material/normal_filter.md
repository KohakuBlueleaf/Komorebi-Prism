# The normal filter

A normal map is read through its mip chain, one level a triangle. On a fabric seen from a
few metres, a pixel covers many of the map's bumps. Its texel used to be a
renormalised average, which is a single bent normal. Neighbouring pixels then took
different bent normals, and the lit surface broke into blotches that Cycles, which
averages many rays over the same pixel, does not show. The filter keeps what the average
loses, the spread of the normals under the pixel, and reads it back as a wider and
dimmer response. It is how every normal map is read; there is no option.

## What the mip chain keeps

`scene.public.textures.texture_levels`, role `normal` (a map that is not grey):

1. **Level 0 unit.** Each texel's vector is made unit (`unit_normals`). Maps are often
   stored with lengths other than 1 (compressed or hand-painted), and the length is the
   filter's only signal, so level 0 must carry none of its own.
2. **The under-surface turn.** A vector with z below `NORMAL_LEAST_Z` (cos 45 degrees) is
   turned about its own azimuth up to that z. Such vectors point under the surface; when
   averaged they cancel the others' z and make lengths that come from the map's
   encoding, not from the surface's roughness. The turn comes before any averaging.
3. **The levels averaged, not renormalised.** Each level is the plain mean of the four
   texels under it, so its length r (0 to 1) is the spread of the unit vectors below
   it: 1 where they agree, smaller where they scatter.

The chains are kept under the cache root keyed by `materials.LEVELS_VERSION` (2 since
the filter), so the chains of a scene opened before are rebuilt at its next conversion
(the converter's number is 7).

What the turn changes, measured on lynxsdesign's fabric bump maps (mean length at levels
0 / 2 / 4): 0.787 / 0.171 / 0.068 before, 0.914 / 0.723 / 0.712 after. Before it, the
vectors pointing under the surface cancelled at the coarse levels, and those levels read
as almost all spread.

## How the length is read

Per pixel, from the normal texel `t` as stored (before the normal scale):

- `r = min(|t| / (1 - 1/128), 1)` (`texture.normal_length`): a unit vector rounded to
  bytes is up to 1/128 short, which counts as 1. The white texel a material without a
  normal map reads gives r = 1; glass and emissive materials keep r = 1.
- **Diffuse:** the albedo is multiplied by r. The light a scattered set of normals
  reflects toward the mean direction falls with their spread; to first order it is r.
- **Specular (Toksvig):** the Blinn-Phong exponent s becomes
  `s' = max(rint(r s / (r + s (1 - r))), 1)`, and an exponent 0 (no specular term) stays
  0 (`texture.filtered_exponent`). This is Toksvig's `1/s' = 1/s + (1 - r)/r` rounded
  to the material word's integer exponent. The lobe's colour is multiplied by
  `(1 + s') / (1 + s)`, so the widened lobe keeps its energy in Blinn-Phong's
  normalisation instead of brightening.

### Why Toksvig and not a von Mises-Fisher fit

The described-light model (GGX) widens alpha by a vMF fit,
`alpha'^2 = alpha^2 + 2 / kappa` with `kappa = (3 r - r^3) / (1 - r^2)`. Written in
alpha, Toksvig is `alpha'^2 ~ alpha^2 + 2 (1 - r) / r`; the two agree for r near 1 and
part at low r (at r = 0.17, 9.8 against 3.85). In the reference frames of italian_flat
and lynxsdesign, Toksvig and vMF give the same picture to within 3 levels; no pixel
differs by more than 4. The bumped fabrics have exponents 1 to 4, where both round to the
same s'. Toksvig acts on the integer exponent that the card's material word already
carries, so it is the formula for both models; in alpha it reads
`alpha'^2 = alpha^2 + 2 (1 - r) / r`.

## On the card

The lit pack thread makes a row's surface in two steps (`kernels/pack/lit/surface.hpp`,
and its copy in `steps/kernels/lit/`).

- **On the vector unit** (`surface_row`), with the normal texel already in Dst: `|t|^2`
  by three multiply-adds, its reciprocal square root (`rsqrt_vector`), `|t|` by one
  multiply, times `128/127`, then the minimum with 1. The albedo's three channels are
  multiplied by r, and r is stored in a free vector of the row (`kGLength`, the tangent's
  first, no longer needed once the normal is made). About 12 operations a pixel, and no
  new bytes or fetches.
- **On the pack CPU's vector extension** (`surface_out`), where the material word is
  gathered: s from the word, `D = r + s (1 - r)`, then `q = 1 / (D (1 + s))`, which gives
  both `s' = rint(r s (1 + s) q)` and the lobe `(1 + s') D q` from one reciprocal. The
  specular rows are multiplied by the lobe, and the word goes out with s' in place of s.

### The reciprocal's Newton steps

The pack CPU has no vector divide: `vfdiv` and the estimates (`vfrec7`) are absent, and
Komorebi's load refuses a kernel holding one (`KernelInstructionError`). The reciprocal is
`y0 = bits(0x7EF311C3 - bits(x))`, a first guess with about 12 % error, then three Newton
steps `y = y (2 - x y)`: 12 % becomes about 1.4 %, then 2e-4, then float precision. Over
every exponent 0 to 255 and 20,001 lengths it gives the reference's s' everywhere but 6
exact .5 ties of the rounding, and the lobe to 3e-7.

### Why the values go through the row's window vectors

The values are kept in Dst rather than in registers: s (`kGExponent`), D (`kGSpread`),
`r s` (over `kGLength`) and q (`kGReciprocal`). A compiler barrier between the phases
makes each one read again. Kept in registers, the 8-register groups (LMUL 8) of
`s, r, D, q` and the reciprocal's temporaries outnumber the 32 vector registers. The
compiler then spills whole groups, and `shade_lit` reserved `28 x vlenb` of stack for
them, against `8 x vlenb` before. Komorebi's stack check counts a reservation written as
`slli` of vlenb but not one written as `li 28; mul`, so it reported the old margin while
the stack overflowed by about 290 bytes, and lit sponza hung with no report. Staged
through the window, at most three groups are live at once, the reservation is back to
`8 x vlenb`, and the stage's need equals main's (TRISC2: 1,536 B lit, 1,584 B
gi_threads).

## What it gives

Card pictures against Cycles on the same glTF (patchiness: the mean step between 8 x 8
block means, as a % of the crop's mean):

| crop | Cycles | without the filter | with it |
|---|---:|---:|---:|
| lynxsdesign armchair | 3.9 | 9.4 | 4.3 |
| lynxsdesign sofa | 9.8 | 23.6 | 11.9 |

italian_flat's fabric maps are almost flat (r = 0.99 at every level), and the filter does
not change them.
