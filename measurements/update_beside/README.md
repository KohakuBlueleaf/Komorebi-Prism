# The field's update beside the frames

The preset `gi_tile` (`configs/pipeline/gi_tile.py`) with the build option
`update_beside`: the units of `indirect.field_update` and `indirect.transport` run on work
cluster 2, the update is submitted beside the frames, frames go on with the old field, and
the new field is swapped in between two frames by one write of LIGHT's table
(`stages/indirect/field_update/README.md`, "Beside the frames"). The control is the
preset `gi`, whose loop sends `sun`, then `update`, and waits for both before the next
frame.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz before and after every
  run as the runs report it.
- Date: 2026-11-26 (UTC+8), Komorebi 0.5.3 at e908d6d16; every record from one build of
  the tree, each case's `gi_tile` and `gi` runs one after the other.
- Each case: `scripts/run/preset.py --pipeline P --scene S --view overview --size W H
  --card 1 --check prism.check.field_frames.check`, P `gi_tile` or `gi`: the sun
  (120, 40), then (200, 30), 16 frames each, bounces 2. The record is
  `<scene>_overview_<W>_<H>_<P>.json`.
- The check records, for each sun: the frames drawn before the update's field was in
  (`during`), the frame the swap came before (`swap_frame`) and its picture's sha256, the
  gap between two frames' ends on the host (`net_ms` leaves out the reads of pictures
  between them; the judging is done after the frames), each frame's card time and the
  director's resubmits since the frame before; after the stop the update's times row on
  cluster 2 and the core steps (`core_steps`: each step's round trip from cluster 2 and the
  director's own time).

## Pictures

The first frame after the swap against the frame `gi` draws after its blocking update at
the same sun: the same bytes in all 8 comparisons (equal sha256). Every code 0 in both
presets; the field against the reference's and the scale words pass as in `gi`. The first
frame drawn during the update (the new sun's shadow map, the old field) against the last
frame at the sun before (none for the first sun) and against the first frame after the
swap: pixels that differ / the largest byte difference.

| case | sun | swap before frame | after the swap vs `gi` | during vs before | during vs after |
| --- | --- | ---: | --- | --- | --- |
| sponza 1024x1024 | (120, 40) | 11 | 0 bytes | - | 1,008,887 / 93 |
| sponza 1024x1024 | (200, 30) | 10 | 0 bytes | 100,611 / 189 | 928,999 / 33 |
| bistro_interior 1024x1024 | (120, 40) | 10 | 0 bytes | - | 91,436 / 2 |
| bistro_interior 1024x1024 | (200, 30) | 8 | 0 bytes | 56,438 / 92 | 487,764 / 15 |
| modern_hall 1024x1024 | (120, 40) | 15 | 0 bytes | - | 746,688 / 41 |
| modern_hall 1024x1024 | (200, 30) | 11 | 0 bytes | 13 / 151 | 992,793 / 84 |
| sponza 1920x1080 | (120, 40) | 9 | 0 bytes | - | 2,030,669 / 93 |
| sponza 1920x1080 | (200, 30) | 8 | 0 bytes | 71,459 / 186 | 1,917,108 / 28 |

The reference of the frames during an update (the new sun's direct light with the old
field) is not made by the check; the table gives their difference from the frames before
and after instead.

## Times

In ms. The stop: the gap on the host from the sun's control set to the end of the first
frame at that sun; `gi`'s holds the sun's pass and the blocking update (its card time in
brackets), `gi_tile`'s the sun's pass alone. During: the frames drawn before the swap,
their card times, the steady frame's card time (the median after the swap), the longest
gap from frame 2 to the swap frame against the steady gap (median after the swap). The
update: from its submit to its event seen by the loop (host), and its card time on
cluster 2 (the times row's total).

| case | sun | `gi` stop (update) | `gi_tile` stop | frames during | their card times | steady card | longest gap during | steady gap | update host | update card |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| sponza 1024x1024 | (120, 40) | 669.78 (128.87) | 499.01 | 10 | 16.05, 13.60, 13.58, 13.65, 13.72, 13.68, 13.58, 13.59, 13.57, 13.70 | 13.58 | 16.34 | 13.92 | 148.80 | 147.11 |
| sponza 1024x1024 | (200, 30) | 258.62 (112.42) | 126.15 | 9 | 13.84, 13.56, 13.56, 13.69, 13.61, 13.56, 13.53, 13.54, 13.63 | 13.54 | 16.32 | 13.87 | 132.13 | 130.50 |
| bistro_interior 1024x1024 | (120, 40) | 647.97 (133.77) | 500.25 | 9 | 23.46, 20.37, 20.37, 20.47, 20.35, 20.26, 20.23, 20.25, 20.54 | 20.25 | 24.80 | 20.62 | 199.45 | 183.34 |
| bistro_interior 1024x1024 | (200, 30) | 261.17 (119.44) | 141.87 | 7 | 20.53, 20.32, 20.39, 20.35, 20.23, 20.26, 20.54 | 20.23 | 24.70 | 20.55 | 155.00 | 151.86 |
| modern_hall 1024x1024 | (120, 40) | 678.19 (178.26) | 488.37 | 14 | 13.68, 13.13, 13.14, 13.14, 13.13, 13.15, 13.20, 13.31, 13.27, 13.14, 13.12, 13.14, 13.13, 14.16 | 13.14 | 17.13 | 14.06 | 199.67 | 197.84 |
| modern_hall 1024x1024 | (200, 30) | 243.32 (127.70) | 114.33 | 10 | 13.39, 13.08, 13.13, 13.24, 13.17, 13.08, 13.07, 13.07, 13.06, 14.09 | 13.07 | 17.08 | 13.39 | 144.88 | 140.74 |
| sponza 1920x1080 | (120, 40) | 626.67 (122.52) | 517.66 | 8 | 24.11, 21.59, 21.86, 21.72, 21.94, 21.59, 21.87, 21.59 | 21.71 | 24.57 | 22.15 | 187.46 | 165.87 |
| sponza 1920x1080 | (200, 30) | 251.82 (115.19) | 137.34 | 7 | 22.18, 21.62, 21.97, 21.67, 21.83, 21.57, 21.83 | 21.57 | 24.57 | 22.14 | 163.41 | 141.90 |

No frame is held for the update: the longest gap during it is 2.4 to 3.7 ms over the
steady gap. The first sun's stop holds host work of that first change (both presets,
about 0.5 s); `gi`'s stop is `gi_tile`'s plus about the update. The update takes 12 to 35
ms more on the card beside the frames than blocking: each apply waits for the director to
finish the frame it is in, and its copies wait for the slot.

## Core steps and resubmits

The transport's two applies of each update, run by the director as `core_step`: the round
trip from cluster 2 (it waits for the frame the director is in) and the director's own
time, in ms; every code 0.

| case | steps | round trip | director's |
| --- | ---: | --- | --- |
| sponza 1024x1024 | 4 | 7.796, 7.810, 2.913, 7.755 | 2.614, 2.629, 2.624, 2.623 |
| bistro_interior 1024x1024 | 4 | 20.835, 20.815, 17.391, 6.029 | 4.313, 4.315, 4.315, 4.308 |
| modern_hall 1024x1024 | 4 | 6.471, 12.824, 4.119, 12.764 | 3.824, 3.816, 3.829, 3.824 |
| sponza 1920x1080 | 4 | 23.107, 18.798, 3.193, 18.797 | 2.622, 2.621, 2.625, 2.630 |

The director's core commands submitted again after a busy rejection (cluster 2's copy held
the program's one slot): an update's, over the frames drawn during it, and the frames'
after the swap; `gi`'s over all its frames.

| case | sun | `gi_tile` during | `gi_tile` after | `gi` |
| --- | --- | ---: | ---: | ---: |
| sponza 1024x1024 | (120, 40) | 6 | 0 | 0 |
| sponza 1024x1024 | (200, 30) | 6 | 0 | 0 |
| bistro_interior 1024x1024 | (120, 40) | 6 | 0 | 0 |
| bistro_interior 1024x1024 | (200, 30) | 6 | 0 | 0 |
| modern_hall 1024x1024 | (120, 40) | 6 | 0 | 0 |
| modern_hall 1024x1024 | (200, 30) | 6 | 0 | 0 |
| sponza 1920x1080 | (120, 40) | 4 | 0 | 0 |
| sponza 1920x1080 | (200, 30) | 5 | 0 | 0 |

## Running

```bash
python scripts/run/preset.py --pipeline gi_tile --scene S --view overview --size W H --card 1 --check prism.check.field_frames.check
```
