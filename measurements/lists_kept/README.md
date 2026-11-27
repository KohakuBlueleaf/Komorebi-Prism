# The eye's lists kept while its view stands

A frame of the threads' form whose eye camera, size and run are those of the frame
before runs the tile pull alone on the records, slices' words and lists the last whole
view left ([dispatch](../../docs/internals/program/dispatch.md)). This folder compares
that standing frame with the whole frame (count, sums, place and tile) at the same
camera.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz and its PCIe link at
  16.0 GT/s before and after every run as the runs report it; the card held by each
  run alone (a lock a run), host work on 12 CPUs.
- Date: 2026-11-27 (UTC+8). Preset `gi_threads`, 1,920 x 1,080, the tile pull
  `prefer`, `range_blocks` as the host chooses it, every other option the preset's; no
  account.
- Each run: one load, then 6 frames at each of three poses in turn (the view's camera,
  the viewer's first pose, the first pose turned 90 degrees). The first frame of a
  pose is a whole frame, frames 2 to 6 stand. A number is the median over frames 2 to 6
  of a pose, then the median of three runs. The whole frames are the three runs of
  [threads_ranges](../threads_ranges/README.md) at the chosen size, before the lists
  were kept (every frame whole).
- Every frame of every run: code 0, no retry, no reload; frames 2 to 6 ran no count
  range (the times row's `dispatch_ranges` 0). The last picture of each pose of every
  run equal byte for byte to the picture of the whole frame at 4 blocks a range (36 of
  36).
- `checks.lists_kept` on sponza, italian_flat_97f97a20ba and lynxsdesign_411c9daef8
  (card 0): the sequence stand, stand, the sun moved, stand, stand, a control set,
  stand, the pose turned, stand, a smaller size, stand, a larger size, stand, a reload,
  stand: every frame's kind the one asked for (whole after the sun, the pose, a size
  and the reload; the tile alone otherwise) and every picture equal to the load that
  counts every frame.

## Frame (ms), whole and standing

| scene | pose | range_blocks | whole frame | count + sums + place | standing frame | tile |
|---|---|---:|---:|---:|---:|---:|
| sponza | view camera | 4 | 18.6 | 3.25 | 15.5 | 15.45 |
| | viewer first pose | 4 | 18.6 | 3.23 | 15.5 | 15.45 |
| | turned 90 | 4 | 14.1 | 2.61 | 11.6 | 11.59 |
| italian_flat_97f97a20ba | view camera | 16 | 40.5 | 12.31 | 28.8 | 28.69 |
| | viewer first pose | 16 | 38.3 | 11.73 | 26.7 | 26.69 |
| | turned 90 | 16 | 21.6 | 8.79 | 12.9 | 12.85 |
| lynxsdesign_411c9daef8 | view camera | 21 | 45.0 | 18.24 | 27.0 | 26.89 |
| | viewer first pose | 21 | 45.5 | 18.39 | 27.2 | 27.15 |
| | turned 90 | 21 | 27.7 | 13.94 | 13.9 | 13.80 |
| lynxsdesign_a01894bbb8 | view camera | 39 | 84.5 | 50.10 | 34.4 | 34.37 |
| | viewer first pose | 39 | 85.1 | 50.30 | 34.8 | 34.78 |
| | turned 90 | 39 | 62.0 | 41.04 | 21.1 | 21.04 |

A standing frame keeps of the phases before the tile pull only the running sum over
the slices and the steps' frame words (0.10 ms together); its tile pull takes what the
whole frame's does.
