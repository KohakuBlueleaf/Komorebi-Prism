# The renderer's frame: `gi` and `gi_threads`

The frame's time on the card of the renderer, the preset `gi_threads` (the lit frame
with the indirect field, run as threads the cores take), against its stage-wise form,
the preset `gi`, on ten scenes, at 1,920 x 1,080 on every core. Each preset with its own
options: nothing was tuned for these numbers. Then the field's update after the sun is
moved once.

- Card: one Blackhole P150A, 120 cores, AICLK 1,350 MHz before and after every run as
  the runs report it, its PCIe link at 16.0 GT/s at every run's start and end. The frames
  on card 1, the update on card 0; each card shared with other jobs by a lock, held by a
  run alone while it ran.
- Date: 2026-11-28 (UTC+8), Komorebi 0.6.0, main at f614f61.
- The scenes: the six public scenes with their materials made again at this tree's
  converter; the four artists' scenes converted by `prism_cli open` at this tree's
  converter (a converted name carries ten hex digits of its file's digest, so a scene
  converted again under a new converter has a new name). Every scene's far field built.
- Each case: `scripts/run/threads_account.py --pipeline gi --scene S --view V --size
  1920 1080 --frames 64 --way W --want PICTURE --card C`, W `stagewise` (the preset
  `gi`; it writes its first picture) or `prefer` (the preset `gi_threads`; `prefer` is
  its host's own tile pull's choice). One load, 64 frames at the view's camera; no sun
  is moved.
- `gi_threads` twice: as a standing camera (`--keep-lists`: the preset's default, the
  loop keeps a frame's lists while the view does not change, and the frame runs the tile
  pull alone), and with the lists made again every frame (the script's default: the
  count, sums and place pulls run each frame, as when the camera moves).
- Three runs a case, interleaved (scene by scene `gi`, `gi_threads` made again,
  `gi_threads` standing; three rounds over the ten scenes). A run's number is the median
  over frames 2 to 64; the number given is the median of the three runs, the range the
  three runs' medians.
- Every frame of every run: code 0. Pictures: every `gi_threads` frame against the
  picture `gi`'s run of the same round wrote, by the threads' frame check's comparison
  (`prism.check.threads.compare.pictures`, byte for byte): 0 pixels different in all
  3,840 frames; every `gi` frame equal to its run's first.
- The raw records stay on disk, outside the repository.

## The frame

ms. `gi` pushes its picture to the host inside its frame (`push`, 0.564 ms on every
scene, the preset's option `push` true); `gi_threads` does not (its option `push`
false): the column "`gi` less push" is the like frame, and each ratio is over it.
"Moves" is `gi_threads` with its lists made again every frame, "stands" with them kept.

| scene (view) | `gi` (runs' range) | `gi` less push | `gi_threads` moves (runs' range) | `gi_threads` stands (runs' range) | ratio moves | ratio stands | pictures |
|---|---|---:|---|---|---:|---:|---|
| sponza (overview) | 24.689 (24.683 to 24.804) | 24.125 | 20.003 (19.978 to 20.040) | 16.795 (16.742 to 16.813) | 0.83 | 0.70 | equal |
| bistro_interior (overview) | 36.226 (36.224 to 36.228) | 35.663 | 25.247 (25.237 to 25.295) | 21.154 (21.143 to 21.156) | 0.71 | 0.59 | equal |
| breakfast_room (overview) | 19.985 (19.984 to 19.987) | 19.421 | 16.341 (16.337 to 16.342) | 14.056 (14.043 to 14.072) | 0.84 | 0.72 | equal |
| salle_de_bain (overview) | 23.908 (23.907 to 23.918) | 23.344 | 19.696 (19.694 to 19.697) | 16.010 (16.002 to 16.012) | 0.84 | 0.69 | equal |
| modern_hall (overview) | 25.457 (25.456 to 25.460) | 24.893 | 19.384 (19.357 to 19.509) | 18.370 (18.250 to 18.380) | 0.78 | 0.74 | equal |
| modern_living_room (overview) | 27.520 (27.519 to 27.522) | 26.956 | 20.089 (20.077 to 20.098) | 15.149 (15.146 to 15.158) | 0.75 | 0.56 | equal |
| classroom_3f4180c5d0 (camera) | 34.581 (34.578 to 34.582) | 34.017 | 26.514 (26.425 to 26.562) | 22.037 (22.036 to 22.096) | 0.78 | 0.65 | equal |
| lynxsdesign_b49574c042 (camera) | 58.580 (58.579 to 58.582) | 58.016 | 43.664 (43.645 to 43.672) | 29.433 (29.413 to 29.453) | 0.75 | 0.51 | equal |
| italian_flat_69651f32b4 (camera) | 52.888 (52.887 to 52.889) | 52.324 | 40.904 (40.887 to 40.924) | 29.680 (29.615 to 29.746) | 0.78 | 0.57 | equal |
| lynxsdesign_6efc48febc (camera) | 101.142 (101.140 to 101.144) | 100.578 | 67.163 (67.153 to 67.170) | 37.753 (37.749 to 37.784) | 0.67 | 0.38 | equal |

Triangles drawn: classroom_3f4180c5d0 1,252,126; lynxsdesign_b49574c042 8,806,420;
italian_flat_69651f32b4 4,821,520; lynxsdesign_6efc48febc 29,756,735.

## By phase

The median of the three runs' medians, ms. `gi`: its commands grouped: raster the
raster's passes over both layers (count, sum, take, heavy, hist, hsum, cut, sort, assign,
compact, pages, give, middle, place, setup, fill); shade both layers; light with its
glass form; show; push. `gi_threads`: the dispatcher's phases: count, sums, running (the
running sum), place (the set-up pass and the list writes together), tile (every step of
a tile thread: fill, shade, light with the field, show); words take 0.002 ms in every
row. The two forms' phases do not stand against each other one for one: the threads'
place holds the stage-wise set-up, its tile the stage-wise fill, shade, light and show.
Standing, count and place take under 0.005 ms and the running sum 0.04 to 0.06 ms:
the frame is the tile pull.

| scene | `gi` raster | `gi` shade | `gi` light | `gi` show | `gi` push | moves: count | sums | running | place | tile | stands: tile |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sponza | 9.902 | 7.436 | 7.285 | 1.535 | 0.564 | 1.079 | 0.324 | 0.052 | 1.879 | 16.720 | 16.735 |
| bistro_interior | 17.023 | 9.409 | 10.739 | 1.541 | 0.564 | 1.298 | 0.459 | 0.063 | 2.394 | 21.081 | 21.084 |
| breakfast_room | 6.862 | 4.473 | 7.572 | 1.614 | 0.564 | 0.787 | 0.187 | 0.042 | 1.339 | 14.012 | 14.008 |
| salle_de_bain | 9.114 | 5.872 | 7.911 | 1.555 | 0.564 | 1.260 | 0.189 | 0.043 | 2.289 | 15.951 | 15.961 |
| modern_hall | 5.452 | 4.620 | 14.927 | 1.583 | 0.564 | 0.391 | 0.324 | 0.053 | 0.414 | 18.267 | 18.311 |
| modern_living_room | 11.556 | 5.429 | 10.588 | 1.620 | 0.564 | 1.555 | 0.324 | 0.054 | 3.110 | 15.092 | 15.091 |
| classroom_3f4180c5d0 | 15.717 | 8.304 | 11.304 | 1.546 | 0.564 | 1.486 | 0.458 | 0.062 | 2.488 | 22.072 | 21.967 |
| lynxsdesign_b49574c042 | 32.742 | 12.527 | 13.202 | 1.528 | 0.564 | 4.610 | 0.324 | 0.052 | 9.324 | 29.371 | 29.375 |
| italian_flat_69651f32b4 | 26.237 | 12.691 | 13.722 | 1.555 | 0.564 | 3.778 | 0.325 | 0.053 | 7.157 | 29.611 | 29.621 |
| lynxsdesign_6efc48febc | 72.845 | 14.544 | 13.536 | 1.577 | 0.564 | 9.565 | 0.323 | 0.052 | 19.545 | 37.722 | 37.694 |

`gi_threads` is the faster frame on every scene: 0.67 to 0.84 of `gi` less its push with
its lists made again, 0.38 to 0.74 standing. On the largest scene the count and place
pulls take 29.1 ms against 72.8 ms for the stage-wise raster's passes with fill
included.

## 3,840 x 2,160

Sponza's overview at 3,840 x 2,160, `gi_threads`, the same conditions and three runs a
case (64 frames, card 1): 66.505 ms with the lists made again (66.500 to 66.518), 57.082
ms standing (57.072 to 57.096); every code 0. `gi` does not load at that size: its
program's buffers do not fit a core's L1 (the load is refused with the numbers). The
picture against the reference instead (`python -m prism_cli run --pipeline gi_threads
--scene sponza --view overview --size 3840 2160 --frames 16 --check 0 15`, card 0):
frames 1 and 16 each with shares of pixels over 2 / 4 / 8 of 255 apart 0.000169 /
4e-05 / 1e-05, the largest error 96 (on shadow edges); its frame 57.11 ms.

## The field's update after one sun move

One run a preset a scene (a scratch driver around `prism.check.field_frames.at_sun`,
whose `check` reads the update's times from the stage-wise region and stops on the
threads' form, where they are in the job thread's region): the preset loaded, 8 frames,
the sun set to (120, 40) through the loop's control, 32 frames at the view's camera.
The update's passes are the scene's own count ("bounces", set by the scene). Every code
0, the update's code 0 in both.

`gi` sends the sun's pass and the update before the next frame and waits for them: its
first frame at the new sun is the stop (host ms from the control set to that frame's
end) and the update's card time is its times row's total (50 MHz timer). `gi_threads`
runs the update as the job thread's graph beside the frames, each apply a step of every
core between two frames: frames during are the frames drawn with the old field, the swap
is the first frame with the new one. The first frame at the new sun is the longest gap
on the host (the sun's pass and the host's work of the change are in it).

| scene | bounces | `gi` stop | `gi` update (card) | `gi_threads` frames during | their card ms | steady card ms | first frame at the new sun (host) | sun set to swap frame's end | job thread's own time |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| sponza | 3 | 173.4 | 108.1 | 5 | 16.7 to 20.0 | 16.74 | 60.9 | 161.4 | 95.9 |
| bistro_interior | 2 | 203.5 | 106.8 | 4 | 21.0 to 25.2 | 21.14 | 67.0 | 167.5 | 96.0 |
| breakfast_room | 12 | 188.6 | 134.3 | 14 | 14.0 to 16.3 | 13.98 | 55.4 | 288.8 | 211.0 |
| salle_de_bain | 10 | 270.6 | 200.3 | 12 | 16.1 to 19.7 | 16.07 | 61.0 | 298.7 | 206.4 |
| modern_hall | 10 | 240.5 | 188.5 | 13 | 17.5 to 19.7 | 18.13 | 43.9 | 330.5 | 231.0 |
| modern_living_room | 15 | 350.9 | 287.0 | 19 | 15.2 to 20.1 | 15.24 | 64.7 | 425.1 | 305.9 |
| classroom_3f4180c5d0 | 3 | 192.4 | 104.0 | 5 | 21.9 to 26.5 | 22.03 | 74.1 | 202.9 | 120.9 |
| lynxsdesign_b49574c042 | 5 | 293.7 | 153.5 | 7 | 29.3 to 43.7 | 29.43 | 92.5 | 320.6 | 168.3 |
| italian_flat_69651f32b4 | 8 | 277.8 | 136.5 | 9 | 29.5 to 41.0 | 29.64 | 112.3 | 409.1 | 285.4 |
| lynxsdesign_6efc48febc | 8 | (did not end) | | 10 | 37.6 to 67.2 | 37.78 | 147.8 | 567.5 | 342.0 |

The first frame during the update, at the new sun, takes the time of the frame with its
lists made again in the table above (Sponza 20.0, the largest scene 67.2 ms); the others
take the steady frame's. The job thread's own time is the sum of its commands' times (fetch,
zero, sources, rows, pack, store): the applies run as the frames' thread's steps and are
not in it, so it is not the update's span; the span as the host sees it is the column
"sun set to swap frame's end". `gi`'s run on lynxsdesign_6efc48febc did not end: its
load ended and no frame after the sun's move did within the run's 900 s.

## A traced update, 2026-11-27

The update traced on the card, each apply the frame's thread's `core_step` on every core
between two frames, as above. One run a scene, 2026-11-27, card 1 at 16 GT/s, AICLK 1,350
MHz, the account and the trace on, two passes of the transport (the count then given to
every scene): the preset loaded, 4 frames, the sun moved to (120, 40) through the loop's
control, frames back to back until past the swap. "Card span" is from the job thread's
first command to the end of the first frame with the new field, on the card's clock (the
trace); "host" from the control set to that frame's end. Every code 0; the swap frame's
picture equal, byte for byte, to `gi`'s first frame at that sun.

| scene | frames during | ms (steady) | applies, ms each | card span | host |
|---|---:|---|---:|---:|---:|
| sponza | 5 | 18.63 to 19.55 (18.70 to 18.88) | 2.60 | 145.3 | 348.0 |
| italian_flat_97f97a20ba | 2 | 42.26 (41.93 to 42.68) | 2.70 | 178.0 | 494.1 |
| lynxsdesign_a01894bbb8 | 4 | 101.70 to 102.33 (102.06 to 102.24) | 3.92 | 528.8 | 797.3 |

An apply waits for the frame in progress to end, and the field's hand-over waits behind
a frame already sent: the span grows by part of a frame per apply and by up to one frame
at the swap.

## What it does not show

- The frames are at the view's camera with no sun moved: a camera that moves is stood
  for by the lists made again every frame, not by a moving path (reloads, recoveries).
- The account (build option `account`) was off: no core's time, no bytes, no records.
- `gi`'s push and `gi_threads`' lack of it are the presets' own options, not
  equalised; the frame less push is given beside.
- The update's table is one run a scene; its host columns hold host time (the loop's
  Python, the reads), not the card's alone.
- The other ways of handing out (`order`, `kept`) and a tile cut (`heavy`) were not run
  for `gi_threads`.

## The account script through the loop

`scripts/run/threads_account.py` imported an adapter of the checks
(`checks/threads_frame/threaded.py`) that was removed when the threads' presets came to
run through the loop (`prism.loop.Loop`, its form chosen by `prism.program.form`). It
now opens the threads' preset as any preset (`Opened.open`, the real loop; the hosts'
commands sent before each FRAME as the loop sends them), and the account's reader takes
the frame host from the loop's assembled program. Its options, record and columns are
unchanged. Proof, one run each, `textured`, Sponza's overview, 16 frames, `prefer`:
13.093 ms without the account and 13.169 ms with `--account 512` (the threads' account
page: 13.134 ms, range 13.072 to 13.188); every frame code 0 and equal to the stage-wise
picture; the account's 16 frames read, no record lost.

## Running

```bash
python scripts/run/threads_account.py --pipeline gi --scene S --view V --size 1920 1080 --frames 64 --way stagewise --want W.npy --out GI.json --card 1
python scripts/run/threads_account.py --pipeline gi --scene S --view V --size 1920 1080 --frames 64 --way prefer --want W.npy --out GI_THREADS.json --card 1
python scripts/run/threads_account.py --pipeline gi --scene S --view V --size 1920 1080 --frames 64 --way prefer --keep-lists --want W.npy --out GI_THREADS_STANDING.json --card 1
```
