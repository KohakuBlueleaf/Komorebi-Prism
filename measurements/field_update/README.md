# The field's update on the card: the preset `field`

The preset `field` (`indirect.transport` and `indirect.field_update`) on one Blackhole
P150A, card 1, 120 cores, AICLK 1,350 MHz, its link to the host at 16 GT/s, 2026-11-26
(UTC+8), Komorebi at b5589ff78. The sun is at azimuth 120,
elevation 40, and the shadow map is the reference's for that sun. Each run makes two
`update` commands in one load. The first one also fetches the shadow map for the first
time and zeroes the pages. The records are in `runs/<scene>_b<bounces>[_stepped].json`,
written by `python scripts/run/field.py --scene S --bounces N [--stepped] --card 1`.

## The field against the reference

The update's texels are compared with `expected` (`model/results.py`, the reference's
`element_light` to `pack_field` with the same lights): the share of texels equal, the
largest code difference of a channel, and the scale's relative difference. Every
command's code is 0, and the has-data bits are equal in every case.

The verdict (`check.py` `verdict`) has two rules. Every code must be 0. The largest code
difference must be at most 1 at 0 bounces and in the stepped form, and at most 12 in the
whole form with passes, where the card applies the matrix in its tile formats.

| scene | bounces | form | share equal | code most | scale rel | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| sponza | 0 | whole | 0.99998 | 1 | 2.1e-7 | ok |
| sponza | 0 | stepped | 0.99998 | 1 | 2.1e-7 | ok |
| sponza | 2 | whole | 0.96079 | 5 | 1.1e-7 | ok |
| sponza | 2 | stepped (host float apply) | 0.99047 | 1 | 2.1e-7 | ok |
| bistro_interior | 0 | whole | 0.99994 | 1 | 2.1e-7 | ok |
| bistro_interior | 2 | whole | 0.58642 | 6 | 2.9e-3 | ok |
| modern_hall | 0 | whole | 0.99998 | 1 | 7.6e-8 | ok |
| modern_hall | 2 | whole | 0.83576 | 10 | 1.4e-3 | ok |

Every case is ok. With passes, the whole form multiplies bfp8_b weights by bf16 x, while
the reference's apply is in float32. That is the apply's own error, and the field's
largest value (the scale) follows it.

The scale and the three units LIGHT decodes with are in the times row (`FU_T_SCALE`,
`FU_T_UNIT`). The units agree with (1 / max code)^2 x the reference's scale as closely as
the scale does.

## Times

The thread's ms: the whole update (the first one of a load, then the second), its parts
in the first, and an apply a pass (the larger).

| scene | bounces | update ms 1st / 2nd | sources / rows / pack ms | apply ms a pass |
| --- | --- | --- | --- | --- |
| sponza | 0 | 99.48 / 90.61 | 41.42 / 20.67 / 28.08 | - |
| sponza | 2 | 124.79 / 117.78 | 41.06 / 20.68 / 34.08 | 2.617 |
| bistro_interior | 0 | 115.89 / 94.01 | 26.79 / 30.79 / 39.47 | - |
| bistro_interior | 2 | 154.43 / 125.35 | 26.80 / 36.33 / 41.93 | 4.297 |
| modern_hall | 0 | 153.71 / 109.70 | 38.83 / 22.50 / 43.69 | - |
| modern_hall | 2 | 180.77 / 127.81 | 38.85 / 22.20 / 44.35 | 3.817 |

The rows part varies from run to run: Bistro interior at 2 bounces has it at 36.33 ms in
its first update and 26.98 ms in its second. Each pass, in ms (store / apply / fetch /
next), is in the records under `times[].passes_ms`.

The stepped form's times (Sponza, 2 bounces: about 1.7 s an update on the host, most of
it the host's float apply) are in its record.
