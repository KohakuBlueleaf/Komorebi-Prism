# The walk culled by the view

A count range whose box lies wholly outside the eye's view is neither read nor set up,
in count and in place ([dispatch](../../docs/internals/program/dispatch.md)). This
folder compares whole frames with the cull (`cull` True, the default) and without it
(`cull` False), in one tree.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz and its PCIe link at
  16.0 GT/s before and after every run as the runs report it; the card held by each
  run alone (a lock a run, the runs without and with the cull taken in turn), host work
  on 12 CPUs.
- Date: 2026-11-27 (UTC+8). Preset `gi_threads`, 1,920 x 1,080, the tile pull
  `prefer`, `range_blocks` as the host chooses it (sponza 4, italian_flat_97f97a20ba
  16, lynxsdesign_411c9daef8 21, lynxsdesign_a01894bbb8 39), `keep_lists` False (every
  frame whole), every other option the preset's; no account.
- Each run: one load, then 6 frames at each of three poses in turn (the view's camera,
  the viewer's first pose, the first pose turned 90 degrees). A number is the median
  over frames 2 to 6 of a pose, then the median of three runs, in ms.
- Every frame of every run: code 0, no retry, no reload. The last picture of each pose
  of every run with the cull equal byte for byte to the run without it (36 of 36).
  `checks.threads_frame whole` with the cull on sponza, italian_flat_97f97a20ba and
  lynxsdesign_411c9daef8: every policy equal to the stage-wise frame, its map equal.

| scene | pose | frame without / with | count without / with | place without / with | tile without / with |
|---|---|---:|---:|---:|---:|
| sponza | view camera | 18.61 / 18.61 | 1.04 / 1.04 | 1.81 / 1.78 | 15.48 / 15.43 |
| sponza | first pose | 18.63 / 18.65 | 1.04 / 1.07 | 1.82 / 1.84 | 15.42 / 15.43 |
| sponza | turned 90 | 14.17 / 14.15 | 0.91 / 0.92 | 1.32 / 1.31 | 11.61 / 11.61 |
| italian_flat | view camera | 40.64 / 39.66 | 4.20 / 3.91 | 7.68 / 7.13 | 28.36 / 28.09 |
| italian_flat | first pose | 38.48 / 37.11 | 4.09 / 3.64 | 7.30 / 6.52 | 26.63 / 26.71 |
| italian_flat | turned 90 | 21.64 / 17.31 | 3.69 / 1.89 | 4.72 / 2.23 | 12.91 / 12.87 |
| lynx_411 | view camera | 45.11 / 41.63 | 6.32 / 5.03 | 11.66 / 9.43 | 26.86 / 26.82 |
| lynx_411 | first pose | 45.53 / 41.95 | 6.33 / 5.03 | 11.76 / 9.45 | 27.15 / 27.13 |
| lynx_411 | turned 90 | 27.71 / 19.51 | 5.96 / 2.58 | 7.60 / 2.82 | 13.81 / 13.79 |
| lynx_a01 | view camera | 84.61 / 65.56 | 18.78 / 10.97 | 31.16 / 19.85 | 34.35 / 34.39 |
| lynx_a01 | first pose | 85.21 / 66.14 | 18.82 / 10.99 | 31.23 / 19.99 | 34.82 / 34.78 |
| lynx_a01 | turned 90 | 62.21 / 30.21 | 17.81 / 4.25 | 23.08 / 4.75 | 21.05 / 20.98 |

The share of blocks the test cuts, from the host's form of the same test
(`prism_reference.raster.cull`) at the chosen range size, view camera / first pose /
turned 90: sponza 30.9 / 30.9 / 95.0 %, italian_flat 24.3 / 33.9 / 99.1 %, lynx_411
42.5 / 43.1 / 92.7 %, lynx_a01 58.7 / 58.8 / 95.1 %; no range cut that holds a
triangle with an entry. The layer's triangles sorted by the Morton code of their
centroids before they are cut into blocks change these by under 2.5 points (sponza at
16 blocks a range 24.2 against 21.7, lynx_a01 turned 90 at 39 blocks 95.1 against
97.3), so the blocks keep the file's order.

The account of lynxsdesign_a01894bbb8 at its view camera and the scene's own size
(1,024 x 1,024; `scripts/run/threads_account.py`, account 8,192 records a core, trace
512, `keep_lists` False, 6 frames, its waterfall's table of frame 6):

| phase | span ms without / with | core-ms working without / with | core-ms standing (asked) without / with |
|---|---:|---:|---:|
| count | 17.49 / 9.63 | 2,083.5 / 1,046.4 | 15.0 (1.6) / 108.9 (82.2) |
| place | 26.59 / 15.10 | 3,118.7 / 1,726.4 | 71.6 (3.8) / 85.4 (36.1) |
| tile | 21.90 / 20.63 | 1,758.5 / 1,758.2 | 869.2 / 717.6 |
| frame | 66.55 / 45.95 | | |

With the cull a cut range still costs its ask: count's cores wait 82.2 core-ms for
X280's answers against 1.6 without it, as cut ranges end at once and ask again.
