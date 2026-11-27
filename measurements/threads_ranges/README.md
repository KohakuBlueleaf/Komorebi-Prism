# The size of a count range

The threads' frame's count and place pulls hand a view's triangle blocks out in count
ranges of `range_blocks` blocks (32 triangles a block), one exchange with X280 a range.
This folder compares the fixed 4 blocks a range with the size the threads' host now
chooses from the scene's blocks and the cores (`range_blocks_of`, the rule in
[dispatch](../../docs/internals/program/dispatch.md)).

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz and its PCIe link at
  16.0 GT/s before and after every run as the runs report it; the card held by each
  run alone (a lock a card), host work on 12 CPUs.
- Date: 2026-11-27 (UTC+8). Preset `gi_threads`, 1,920 x 1,080, the tile pull
  `prefer`, every other option the preset's; no account.
- Each run: one load, then 6 frames at each of three poses in turn: the view's camera,
  the viewer's first pose (the camera's eye set ahead onto its near plane, as the viewer
  flies from it) and the first pose turned 90 degrees about the vertical. A number is
  the median over frames 2 to 6 of a pose, then the median of three runs; the runs of
  4 blocks and of the chosen size interleaved (one load each).
- Every frame of every run: code 0, no retry, no reload. The last picture of each pose
  of every run equal byte for byte to the picture of the first run at 4 blocks (72 of
  72), and at every other size tried (8, 16, 35, 64).

## Frame and phases (ms)

`sums` is the sums, the running sum and the steps' frame words together.

| scene | blocks | pose | range_blocks | frame | count | sums | place | tile |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| sponza | 8,196 | view camera | 4 | 18.6 | 1.04 | 0.37 | 1.84 | 15.43 |
| | | viewer first pose | 4 | 18.6 | 1.04 | 0.37 | 1.82 | 15.46 |
| | | turned 90 | 4 | 14.1 | 0.92 | 0.37 | 1.32 | 11.60 |
| italian_flat_97f97a20ba | 150,673 | view camera | 4 | 42.3 | 5.42 | 0.37 | 8.20 | 28.37 |
| | | | 16 | 40.5 | 4.18 | 0.37 | 7.76 | 28.21 |
| | | viewer first pose | 4 | 40.1 | 5.37 | 0.37 | 7.80 | 26.61 |
| | | | 16 | 38.3 | 4.07 | 0.37 | 7.29 | 26.59 |
| | | turned 90 | 4 | 23.7 | 5.37 | 0.37 | 5.11 | 12.85 |
| | | | 16 | 21.6 | 3.67 | 0.37 | 4.75 | 12.86 |
| lynxsdesign_411c9daef8 | 275,201 | view camera | 4 | 49.6 | 9.39 | 0.37 | 12.87 | 26.95 |
| | | | 21 | 45.0 | 6.30 | 0.37 | 11.57 | 26.78 |
| | | viewer first pose | 4 | 49.8 | 9.39 | 0.37 | 12.92 | 27.14 |
| | | | 21 | 45.5 | 6.31 | 0.37 | 11.71 | 27.25 |
| | | turned 90 | 4 | 32.3 | 9.43 | 0.37 | 8.76 | 13.80 |
| | | | 21 | 27.7 | 5.93 | 0.37 | 7.64 | 13.81 |
| lynxsdesign_a01894bbb8 | 929,899 | view camera | 4 | 102.1 | 30.64 | 0.38 | 36.75 | 34.39 |
| | | | 39 | 84.5 | 18.73 | 0.37 | 31.00 | 34.38 |
| | | viewer first pose | 4 | 102.1 | 30.65 | 0.37 | 36.30 | 34.74 |
| | | | 39 | 85.1 | 18.76 | 0.37 | 31.17 | 34.80 |
| | | turned 90 | 4 | 80.6 | 30.91 | 0.37 | 28.19 | 21.06 |
| | | | 39 | 62.0 | 17.75 | 0.37 | 22.92 | 21.02 |

## Other sizes tried (one or three runs, the viewer's first pose)

| scene | range_blocks | runs | frame | count | place |
|---|---:|---:|---:|---:|---:|
| sponza | 8 | 3 | 18.7 | 1.09 | 1.82 |
| italian_flat_97f97a20ba | 35 | 3 | 39.2 | 4.48 | 7.68 |
| lynxsdesign_a01894bbb8 | 64 | 1 | 85.0 | 18.58 | 31.20 |

On the 4.8 M triangle scene 35 blocks a range (36 ranges a core) count more slowly than
16 (78 a core) although they ask less: the end's imbalance outweighs the ranges' own
cost there, the two costs the rule weighs. On the 29.8 M triangle
scene 39 and 64 are within 0.2 ms of each other.

Sponza at larger sizes, measured the same day at the view's camera by another account of
the frame (`scripts/run/threads_account.py`, one run, 15 frames): the frame 18.74, 19.26
and 20.19 ms at 4, 16 and 64 blocks; at 64 one range a core, its longest range 1.83 ms.
