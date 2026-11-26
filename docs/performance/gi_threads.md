# The renderer's frame: `gi_threads` against `gi`

The renderer, the preset `gi_threads` (the lit frame with the indirect field, run as
threads the cores take, [the frame as threads](../concepts/threads.md)), against its
stage-wise form `gi`, on the ten scenes of the viewer's data; then the field's update
after the sun is moved once. Every number is from
[measurements/gi_threads](../../measurements/gi_threads/README.md); this page gives what
they say.

Conditions: one Blackhole P150A, 120 cores, AICLK 1,350 MHz, 2026-11-27 (UTC+8),
Komorebi 0.6.0, 1,920 x 1,080 at the view's camera, every core, each preset with its own
options. 64 frames a load, no sun moved; a run's number is the median over frames 2 to
64, the number given the median of three interleaved runs. Every frame's code 0 and every
`gi_threads` picture equal to `gi`'s, byte for byte, in all 1,920 frames. ms.

## The frame

`gi` pushes its picture into the host's memory inside its frame (its option `push`
true); `gi_threads` does not (the post step writes the display's pages from the cores).
"`gi` less push" is the like frame; the ratio is `gi_threads` over it. The card's PCIe
link ran at 2.5 GT/s during these runs (16 GT/s is its normal speed), so the push in
the column `gi` is 4.440 ms on every scene; at 16 GT/s it is 0.565 ms (measured the
same day on the stage-wise `textured` frame, every other time unchanged), and `gi`'s
frame is then its frame less push plus 0.565 ms.

| scene (view) | `gi` | `gi` less push | `gi_threads` | ratio |
|---|---:|---:|---:|---:|
| sponza (overview) | 26.887 | 22.447 | 18.610 | 0.83 |
| bistro_interior (overview) | 37.722 | 33.282 | 24.182 | 0.73 |
| breakfast_room (overview) | 22.862 | 18.422 | 15.303 | 0.83 |
| salle_de_bain (overview) | 26.282 | 21.842 | 19.189 | 0.88 |
| modern_hall (overview) | 28.406 | 23.966 | 18.639 | 0.78 |
| modern_living_room (overview) | 30.087 | 25.647 | 18.196 | 0.71 |
| classroom_a1c62e93f7 (camera) | 25.834 | 21.394 | 19.170 | 0.90 |
| lynxsdesign_411c9daef8 (camera) | 58.242 | 53.802 | 49.474 | 0.92 |
| italian_flat_97f97a20ba (camera) | 52.464 | 48.023 | 42.224 | 0.88 |
| lynxsdesign_a01894bbb8 (camera) | 98.599 | 94.159 | 102.094 | 1.08 |

The three runs' medians lie within 0.1 ms of each other on every row; the ranges are in
the measurement's table.

## By phase

`gi`'s commands grouped (raster: every pass of both layers, fill included); `gi_threads`'
dispatcher phases (place: the set-up pass and the list writes; tile: every step of a tile
thread). The two do not stand one for one: the threads' place holds the stage-wise
set-up, its tile the stage-wise fill, shade, light and show.

| scene | `gi` raster | shade | light | show | `gi_threads` count | sums | running | place | tile |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sponza | 9.537 | 6.062 | 7.321 | 1.531 | 1.039 | 0.321 | 0.050 | 1.812 | 15.429 |
| bistro_interior | 16.377 | 7.631 | 10.751 | 1.538 | 1.629 | 0.456 | 0.060 | 2.694 | 19.403 |
| breakfast_room | 6.666 | 3.651 | 7.646 | 1.569 | 0.729 | 0.185 | 0.041 | 1.282 | 13.087 |
| salle_de_bain | 8.760 | 4.719 | 7.949 | 1.534 | 1.592 | 0.186 | 0.040 | 2.555 | 14.852 |
| modern_hall | 5.344 | 3.805 | 14.916 | 1.561 | 0.383 | 0.325 | 0.054 | 0.561 | 17.367 |
| modern_living_room | 11.259 | 4.391 | 10.596 | 1.615 | 1.277 | 0.320 | 0.050 | 2.503 | 14.086 |
| classroom_a1c62e93f7 | 7.399 | 3.979 | 9.413 | 1.578 | 1.072 | 0.185 | 0.040 | 1.499 | 16.407 |
| lynxsdesign_411c9daef8 | 31.305 | 9.721 | 13.193 | 1.528 | 9.387 | 0.322 | 0.051 | 12.888 | 26.868 |
| italian_flat_97f97a20ba | 24.911 | 9.416 | 13.889 | 1.573 | 5.410 | 0.322 | 0.051 | 8.200 | 28.259 |
| lynxsdesign_a01894bbb8 | 69.893 | 11.508 | 13.039 | 1.614 | 30.637 | 0.322 | 0.051 | 36.748 | 34.401 |

The steps' words take 0.001 to 0.002 ms in every row.

## The field's update after one sun move

One run a preset a scene: 8 frames, the sun set to (120, 40) through the loop's control,
32 frames. `gi` sends the sun's pass and the update before the next frame and waits:
"stop" is the host's ms from the control set to the end of the first frame at the new
sun, "update" the update's card time. `gi_threads` runs the update as the job thread's
graph beside the frames: "frames during" are drawn with the old field, "to swap" is the
host's ms from the control set to the end of the first frame with the new field. Every
code 0; the field's scale the reference's in both presets.

| scene | `gi` stop | `gi` update | `gi_threads` frames during | their ms | steady ms | longest gap | to swap |
|---|---:|---:|---:|---|---:|---:|---:|
| sponza | 174.5 | 109.9 | 3 | 23.6 to 23.7 | 18.60 | 56.5 | 138.5 |
| bistro_interior | 223.6 | 135.9 | 3 | 31.3 to 31.4 | 24.15 | 72.5 | 179.4 |
| breakfast_room | 161.6 | 104.5 | 3 | 19.6 to 19.7 | 15.24 | 50.1 | 130.7 |
| salle_de_bain | 204.8 | 136.6 | 4 | 25.0 to 25.2 | 19.25 | 70.5 | 183.4 |
| modern_hall | 219.9 | 164.6 | 7 | 23.3 to 23.9 | 18.53 | 47.6 | 231.1 |
| modern_living_room | 243.0 | 174.7 | 6 | 23.3 to 23.6 | 18.23 | 63.4 | 220.2 |
| classroom_a1c62e93f7 | 169.4 | 106.9 | 3 | 24.8 to 25.0 | 19.14 | 65.8 | 161.1 |
| lynxsdesign_411c9daef8 | 322.3 | 164.0 | 3 | 64.8 to 68.4 | 49.43 | 163.5 | 362.6 |
| italian_flat_97f97a20ba | 269.5 | 123.7 | 2 | 55.9 to 55.9 | 42.41 | 144.4 | 259.6 |
| lynxsdesign_a01894bbb8 | 471.6 | 181.4 | 3 | 133.5 to 138.8 | 102.00 | 388.8 | 780.6 |

## What the numbers say

- **The renderer's frame is the faster one on nine scenes**: 0.71 to 0.92 of `gi` less
  its push, 0.60 to 0.85 of `gi` as it runs. A tile's steps (fill, shade, light, show)
  run on the core that took it, its planes kept in L1, as one tile pull.
- **It is behind on the largest scene**, lynxsdesign_a01894bbb8 (102.09 against 94.16 ms
  less push): its count and place pulls take 67.4 ms, against 69.9 ms for all the
  stage-wise raster's passes with fill included, and the tile pull adds 34.4 ms on top.
  On that scene the threads' count and place, not the tile steps, are the frame.
- **The update no longer stops the frames.** `gi` waits 161.6 to 471.6 ms for the sun's
  pass and the update; `gi_threads` draws 2 to 7 frames during it, each 1.25 to 1.36
  times the steady frame (the update's applies hold the lowest ranks). The longest gap
  is the first frame at the new sun, which holds the sun's pass and the host's work of
  the change.

## What is not measured

- A moving camera (reloads, recoveries) and a sun moved during the frame runs.
- The account (no core's time, bytes or records); the other ways of handing out
  (`order`, `kept`) and a tile cut (`heavy`) for `gi_threads`.
- The update's span on the card in the threads' form: the update's columns are one run a
  scene and hold host time.
