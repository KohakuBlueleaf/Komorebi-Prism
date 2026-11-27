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

These frames ran no DEPTH view (the sun stood); they were taken before DEPTH views
were culled too.

The share of blocks the test cuts, from the host's form of the same test
(`prism_reference.raster.cull`) at the chosen range size, the blocks in the file's
order against the layer's triangles sorted by the Morton code of their centroids before
they are cut into blocks; no range cut that holds a triangle with an entry, in either
order:

| scene (blocks a range) | view camera: file / Morton | first pose: file / Morton | turned 90: file / Morton |
|---|---:|---:|---:|
| sponza (4) | 30.9 / 31.4 % | 30.9 / 31.4 % | 95.0 / 95.1 % |
| italian_flat (16) | 24.3 / 25.8 % | 33.9 / 36.0 % | 99.1 / 99.4 % |
| lynx_411 (21) | 42.5 / 42.8 % | 43.1 / 43.6 % | 92.7 / 94.3 % |
| lynx_a01 (39) | 58.7 / 58.8 % | 58.8 / 59.1 % | 95.1 / 97.3 % |

The sort gains under 2.5 points anywhere, so the blocks keep the file's order.

Of the blocks the test keeps, the share whose box lies behind the frame's depth (the
opaque layer's depth buffer at 1,920 x 1,088; a box is behind when its nearest depth is
beyond the farthest depth of every cell its screen rectangle reaches; host arithmetic,
not a cull the card makes), with a count range's box and with each block's own box:

| scene | pose | kept by the test | behind, 32 x 32 cells: range / block box | behind, 8 x 8 cells: range / block box |
|---|---|---:|---:|---:|
| sponza | view camera | 69.1 % | 3.7 / 6.9 % | 5.0 / 9.1 % |
| sponza | first pose | 69.1 % | 3.7 / 6.9 % | 5.0 / 9.1 % |
| sponza | turned 90 | 5.0 % | 5.8 / 5.3 % | 5.8 / 6.3 % |
| italian_flat | view camera | 75.7 % | 44.5 / 47.1 % | 52.4 / 55.6 % |
| italian_flat | first pose | 66.1 % | 38.6 / 43.4 % | 49.8 / 55.0 % |
| italian_flat | turned 90 | 0.9 % | 3.6 / 11.4 % | 3.6 / 11.5 % |
| lynx_411 | view camera | 57.5 % | 24.5 / 26.1 % | 32.4 / 36.2 % |
| lynx_411 | first pose | 56.9 % | 25.5 / 27.7 % | 31.9 / 36.1 % |
| lynx_411 | turned 90 | 7.3 % | 9.5 / 8.1 % | 9.5 / 8.4 % |
| lynx_a01 | view camera | 41.3 % | 12.7 / 24.6 % | 18.0 / 32.4 % |
| lynx_a01 | first pose | 41.2 % | 13.0 / 25.2 % | 16.9 / 32.1 % |
| lynx_a01 | turned 90 | 4.9 % | 0.1 / 0.7 % | 0.1 / 1.2 % |

A DEPTH view is culled by the same test with its own camera and frame: the share of the
DEPTH layers' blocks (opaque and masked) each quadrant of the sun's 2,048 map keeps, its
1,024 x 1,024 frame, the lights' own sun:

| scene (blocks a range) | quadrant 0 | 1 | 2 | 3 | the four together |
|---|---:|---:|---:|---:|---:|
| sponza (4) | 22.1 % | 43.9 % | 51.1 % | 26.6 % | 143.7 % |
| italian_flat (16) | 7.0 % | 6.3 % | 87.0 % | 22.1 % | 122.4 % |

The four quadrants walk 1.44 and 1.22 times the layers' blocks, against 4 times
without the test.

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

## Groups cut where the ranges are dealt

A box a group of `group_ranges` consecutive ranges, tested on the cluster's four X280
cores before the count pull; only the ranges of the groups not cut are dealt, and a
dealt range is still tested by its core. Three ways of dealing were tried on the account
above (lynxsdesign_a01894bbb8, 1,024 x 1,024; the first three rows on card 0, the last
on card 1, both at 16.0 GT/s):

| dealing | count span ms | count X280 ms | count standing, asked core-ms | place span ms | frame ms |
|---|---:|---:|---:|---:|---:|
| every range dealt, cut by its core | 9.63 | 9.74 | 82.2 | 15.10 | 45.95 |
| every range's box tested in `pick` as it is asked | 10.06 | - | 258 | 13.99 | 46.9 |
| every range's box tested first on 4 X280 cores | 7.92 | 12.35 | 1.7 | 14.01 | 46.5 |
| a box a group of 16 ranges tested first on 4 X280 cores | 7.96 | 8.34 | 1.6 | 13.97 | 44.40 |

The X280 reads its region at about 0.74 us a box a core: testing all 23,845 range
boxes there (559 KB) took 4.4 ms of the count phase, a box a group of 16 ranges (1,491
boxes, 35 KB) about 0.3 ms, while the cores' asks for cut ranges disappear in both.

Whole frames as in the first table (card 1, 16.0 GT/s, 2026-11-28, `keep_lists` False,
the median of three runs), with one group a layer (no range dealt is cut at the deal:
the cores' test alone) against groups of 16 ranges; the last picture of each pose of
every run equal byte for byte (36 of 36); `checks.threads_frame whole` on sponza,
italian_flat_97f97a20ba and lynxsdesign_411c9daef8 with groups of 16: every policy equal
to the stage-wise frame, its map equal:

| scene | pose | frame one group / 16 | count one group / 16 | place one group / 16 |
|---|---|---:|---:|---:|
| sponza | view camera | 18.63 / 18.60 | 1.08 / 1.08 | 1.77 / 1.81 |
| sponza | first pose | 18.67 / 18.63 | 1.08 / 1.08 | 1.81 / 1.80 |
| sponza | turned 90 | 13.96 / 13.74 | 0.87 / 0.74 | 1.16 / 1.09 |
| italian_flat | view camera | 39.75 / 39.38 | 3.98 / 3.78 | 7.20 / 6.96 |
| italian_flat | first pose | 37.28 / 36.86 | 3.71 / 3.46 | 6.54 / 6.40 |
| italian_flat | turned 90 | 17.53 / 15.30 | 2.11 / 0.96 | 2.22 / 1.15 |
| lynx_411 | view camera | 41.75 / 40.87 | 5.18 / 4.61 | 9.42 / 9.06 |
| lynx_411 | first pose | 42.16 / 41.17 | 5.18 / 4.61 | 9.50 / 9.13 |
| lynx_411 | turned 90 | 19.66 / 16.61 | 2.80 / 1.07 | 2.74 / 1.41 |
| lynx_a01 | view camera | 65.89 / 63.11 | 11.42 / 9.58 | 19.85 / 18.91 |
| lynx_a01 | first pose | 66.57 / 63.82 | 11.43 / 9.58 | 20.01 / 19.10 |
| lynx_a01 | turned 90 | 30.88 / 26.26 | 4.85 / 2.19 | 4.67 / 2.74 |

The account at each scene's view camera (sponza: overview), 1,024 x 1,024, card 1, one
group a layer against groups of 16 ranges, frame 6 of 6:

| scene | count span ms | count X280 ms | count standing, asked core-ms | place span ms | frame ms |
|---|---:|---:|---:|---:|---:|
| sponza | 0.717 / 0.696 | 0.773 / 0.768 | 2.4 / 2.1 | 1.290 / 1.247 | 11.81 / 11.57 |
| italian_flat | 3.532 / 3.303 | 3.654 / 3.493 | 11.4 / 1.6 | 6.080 / 5.995 | 28.70 / 26.14 |
| lynx_a01 | 9.891 / 7.972 | 10.197 / 8.349 | 113.5 / 1.7 | 15.084 / 13.934 | 45.87 / 44.38 |
