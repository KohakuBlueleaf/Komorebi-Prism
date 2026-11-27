# The renderer's frame: `gi` and `gi_threads`

The frame's time on the card of the renderer, the preset `gi_threads` (the lit frame
with the indirect field, run as threads the cores take), against its stage-wise form,
the preset `gi`, on the ten scenes of the viewer's data, at 1,920 x 1,080 on every core.
Each preset with its own options: nothing was tuned for these numbers. Then the field's
update after the sun is moved once.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz before and after every
  run as the runs report it. The card was held by the runs alone (a lock a card); the
  other card of the machine ran other jobs throughout.
- Date: 2026-11-27 (UTC+8), Komorebi 0.6.0. Tree: main at 3541084 with the account
  script made to run through the loop again (below); every record from one build of
  each preset.
- Each case: `scripts/run/threads_account.py --pipeline gi --scene S --view V --size
  1920 1080 --frames 64 --way W --want PICTURE --card 1`, W `stagewise` (the preset
  `gi`; it writes its first picture) or `prefer` (the preset `gi_threads`; `prefer` is
  its host's own tile pull's choice, so the preset runs as it is given). One load, 64
  frames at the view's camera; no sun is moved.
- Three runs a preset, interleaved (scene by scene, `gi` then `gi_threads`, three
  rounds over the ten scenes). A run's number is the median over frames 2 to 64; the
  number given is the median of the three runs, the range the three runs' medians.
- Every frame of every run: code 0. Pictures: every `gi_threads` frame against the
  picture `gi`'s run of the same round wrote, by the threads' frame check's comparison
  (`prism.check.threads.compare.pictures`, byte for byte): 0 pixels different in all
  1,920 frames; every `gi` frame equal to its run's first.
- The raw records stay on disk, outside the repository.

## The frame

ms. The ratio is `gi_threads` over `gi`. `gi` pushes its picture to the host inside its
frame (`push`, 4.440 ms on every scene, the preset's option `push` true); `gi_threads`
does not (its option `push` false): the column "`gi` less push" is the like frame.

The card's PCIe link ran at 2.5 GT/s during these runs; 16 GT/s is its normal speed.
The link lengthens only what crosses to the host: the push here, and the host columns
of the update's table. Measured the same day after the link was trained again (the
stage-wise `textured` frame on sponza, 1,920 x 1,080, three runs at each speed, with
Komorebi 0.5.3 and 0.6.0 alike): the push 0.565 ms at 16 GT/s against 4.441 ms at
2.5 GT/s, the frame 16.43 against 20.30 ms, every other time the same. So `gi`'s frame
at the normal speed is its frame less push plus 0.565 ms, and the column "ratio"
(with the push) holds for the slow link only.

| scene (view) | `gi` (runs' range) | `gi` less push | `gi_threads` (runs' range) | ratio | ratio less push | pictures |
|---|---|---:|---|---:|---:|---|
| sponza (overview) | 26.887 (26.884 to 26.888) | 22.447 | 18.610 (18.602 to 18.625) | 0.69 | 0.83 | equal |
| bistro_interior (overview) | 37.722 (37.721 to 37.727) | 33.282 | 24.182 (24.181 to 24.189) | 0.64 | 0.73 | equal |
| breakfast_room (overview) | 22.862 (22.860 to 22.863) | 18.422 | 15.303 (15.295 to 15.308) | 0.67 | 0.83 | equal |
| salle_de_bain (overview) | 26.282 (26.279 to 26.282) | 21.842 | 19.189 (19.185 to 19.195) | 0.73 | 0.88 | equal |
| modern_hall (overview) | 28.406 (28.406 to 28.408) | 23.966 | 18.639 (18.554 to 18.649) | 0.66 | 0.78 | equal |
| modern_living_room (overview) | 30.087 (30.086 to 30.089) | 25.647 | 18.196 (18.180 to 18.204) | 0.60 | 0.71 | equal |
| classroom_a1c62e93f7 (camera) | 25.834 (25.832 to 25.836) | 21.394 | 19.170 (19.158 to 19.190) | 0.74 | 0.90 | equal |
| lynxsdesign_411c9daef8 (camera) | 58.242 (58.236 to 58.243) | 53.802 | 49.474 (49.465 to 49.509) | 0.85 | 0.92 | equal |
| italian_flat_97f97a20ba (camera) | 52.464 (52.463 to 52.466) | 48.023 | 42.224 (42.188 to 42.269) | 0.80 | 0.88 | equal |
| lynxsdesign_a01894bbb8 (camera) | 98.599 (98.592 to 98.602) | 94.159 | 102.094 (102.037 to 102.113) | 1.04 | 1.08 | equal |

## By phase

The median of the three runs' medians, ms. `gi`: its commands grouped: raster the
raster's passes over both layers (count, sum, take, heavy, hist, hsum, cut, sort, assign,
compact, pages, give, middle, place, setup, fill); shade both layers; light with its
glass form; show; push. `gi_threads`: the dispatcher's phases: count, sums, running (the
running sum), place (the set-up pass and the list writes together), words, tile (every
step of a tile thread: fill, shade, light with the field, show). The two forms' phases do
not stand against each other one for one: the threads' place holds the stage-wise
set-up, its tile the stage-wise fill, shade, light and show.

| scene | `gi` raster | `gi` shade | `gi` light | `gi` show | `gi` push | `gi_threads` count | sums | running | place | words | tile |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sponza | 9.537 | 6.062 | 7.321 | 1.531 | 4.440 | 1.039 | 0.321 | 0.050 | 1.812 | 0.001 | 15.429 |
| bistro_interior | 16.377 | 7.631 | 10.751 | 1.538 | 4.440 | 1.629 | 0.456 | 0.060 | 2.694 | 0.002 | 19.403 |
| breakfast_room | 6.666 | 3.651 | 7.646 | 1.569 | 4.440 | 0.729 | 0.185 | 0.041 | 1.282 | 0.001 | 13.087 |
| salle_de_bain | 8.760 | 4.719 | 7.949 | 1.534 | 4.440 | 1.592 | 0.186 | 0.040 | 2.555 | 0.001 | 14.852 |
| modern_hall | 5.344 | 3.805 | 14.916 | 1.561 | 4.440 | 0.383 | 0.325 | 0.054 | 0.561 | 0.001 | 17.367 |
| modern_living_room | 11.259 | 4.391 | 10.596 | 1.615 | 4.440 | 1.277 | 0.320 | 0.050 | 2.503 | 0.001 | 14.086 |
| classroom_a1c62e93f7 | 7.399 | 3.979 | 9.413 | 1.578 | 4.440 | 1.072 | 0.185 | 0.040 | 1.499 | 0.001 | 16.407 |
| lynxsdesign_411c9daef8 | 31.305 | 9.721 | 13.193 | 1.528 | 4.440 | 9.387 | 0.322 | 0.051 | 12.888 | 0.002 | 26.868 |
| italian_flat_97f97a20ba | 24.911 | 9.416 | 13.889 | 1.573 | 4.440 | 5.410 | 0.322 | 0.051 | 8.200 | 0.002 | 28.259 |
| lynxsdesign_a01894bbb8 | 69.893 | 11.508 | 13.039 | 1.614 | 4.440 | 30.637 | 0.322 | 0.051 | 36.748 | 0.002 | 34.401 |

On nine scenes `gi_threads` is the faster frame (0.71 to 0.92 of `gi` less its push).
On lynxsdesign_a01894bbb8 it is slower (102.09 against 94.16 ms less push): its count
and place pulls take 67.4 ms against the stage-wise raster's 69.9 ms for all its passes,
fill included, and the tile pull 34.4 ms on top.

## The field's update after one sun move

One run a preset a scene (a scratch driver around `prism.check.field_frames.at_sun`,
whose `check` reads the update's times from the stage-wise region and stops on the
threads' form, where they are in the job thread's region): the preset loaded, 8 frames,
the sun set to (120, 40) through the loop's control, 32 frames at the view's camera.
Every code 0, the update's code 0 in both; the field's scale the reference's within the
same relative difference in both presets on every scene (1e-7 on Sponza, at most 0.0064).

`gi` sends the sun's pass and the update before the next frame and waits for them: its
first frame at the new sun is the stop (host ms from the control set to that frame's
end) and the update's card time is its times row's total (50 MHz timer). `gi_threads`
runs the update as the job thread's graph beside the frames: frames during are the
frames drawn with the old field, the swap is the first frame with the new one.

| scene | `gi` stop | `gi` update (card) | `gi_threads` frames during | their card ms | steady card ms | longest gap during | sun set to swap frame's end | job thread's own time |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| sponza | 174.5 | 109.9 | 3 | 23.6 to 23.7 | 18.60 | 56.5 | 138.5 | 80.2 |
| bistro_interior | 223.6 | 135.9 | 3 | 31.3 to 31.4 | 24.15 | 72.5 | 179.4 | 104.1 |
| breakfast_room | 161.6 | 104.5 | 3 | 19.6 to 19.7 | 15.24 | 50.1 | 130.7 | 80.5 |
| salle_de_bain | 204.8 | 136.6 | 4 | 25.0 to 25.2 | 19.25 | 70.5 | 183.4 | 110.4 |
| modern_hall | 219.9 | 164.6 | 7 | 23.3 to 23.9 | 18.53 | 47.6 | 231.1 | 155.3 |
| modern_living_room | 243.0 | 174.7 | 6 | 23.3 to 23.6 | 18.23 | 63.4 | 220.2 | 153.6 |
| classroom_a1c62e93f7 | 169.4 | 106.9 | 3 | 24.8 to 25.0 | 19.14 | 65.8 | 161.1 | 91.4 |
| lynxsdesign_411c9daef8 | 322.3 | 164.0 | 3 | 64.8 to 68.4 | 49.43 | 163.5 | 362.6 | 154.8 |
| italian_flat_97f97a20ba | 269.5 | 123.7 | 2 | 55.9 to 55.9 | 42.41 | 144.4 | 259.6 | 121.5 |
| lynxsdesign_a01894bbb8 | 471.6 | 181.4 | 3 | 133.5 to 138.8 | 102.00 | 388.8 | 780.6 | 234.8 |

Frames go on during `gi_threads`' update (2 to 7 of them), each 1.25 to 1.36 times the
steady frame. The longest gap during it is the first frame at the new sun (the sun's
pass and the host's work of the change are in it). The job thread's own time is the sum
of its commands' times (fetch, zero, sources, rows, pack, store): the transport's applies
run on the cores the graph queues them on and are not in it, so it is not the update's
span, and it does not stand against `gi`'s total, which holds its applies. The update's
span as the host sees it is the column "sun set to swap frame's end".

## The update with no reserved cores

The table above was taken while an update's applies were queued on the lowest 30 ranks
and the frames ran on the 90 above. Since then each apply is the frame's thread's
`core_step` on every core, run between two frames. One run a tree a scene, 2026-11-27,
card 1 at 16 GT/s, AICLK 1,350 MHz, the account and the trace on: the preset loaded, 4
frames, the sun moved to (120, 40) through the loop's control, frames back to back until
past the swap. "Card span" is from the job thread's first command to the end of the first
frame with the new field, on the card's clock (the trace); "host" from the control set to
that frame's end. Every code 0; the swap frame's picture equal, byte for byte, to `gi`'s
first frame at that sun on all three scenes and both trees.

| scene | frames during, before | ms (steady) | after | ms (steady) | applies after, ms each | card span before | after | host before | after |
|---|---:|---|---:|---|---:|---:|---:|---:|---:|
| sponza | 3 | 23.64 to 23.94 (18.65 to 18.77) | 5 | 18.63 to 19.55 (18.70 to 18.88) | 2.60 | 125.2 | 145.3 | 306.4 | 348.0 |
| italian_flat_97f97a20ba | 1 | 55.95 (42.03 to 42.54) | 2 | 42.26 (41.93 to 42.68) | 2.70 | 144.6 | 178.0 | 375.2 | 494.1 |
| lynxsdesign_a01894bbb8 | 2 | 133.80 to 139.21 (101.69 to 102.26) | 4 | 101.70 to 102.33 (102.06 to 102.24) | 3.92 | 386.0 | 528.8 | 702.3 | 797.3 |

The frames during the update now run on every core at the steady frame's time; each
apply (two at 2 bounces) is a stall between two frames, the apply's time on every core.
An apply waits for the frame in progress to end, and the field's hand-over waits behind
a frame already sent, so the span grows by part of a frame per apply and by up to one
frame at the swap: 20 ms on Sponza, 143 ms on the largest scene. The host span holds the
host's own work of the sun change (110 to 280 ms before the first frame).

## What it does not show

- The frames are at the view's camera with no sun moved and no camera move: what a
  moving view costs (reloads, recoveries) is not here.
- The account (build option `account`) was off: no core's time, no bytes, no records.
- `gi`'s push and `gi_threads`' lack of it are the presets' own options, not
  equalised; the frame less push is given beside.
- The update's table is one run a scene; its host columns hold host time (the loop's
  Python, the reads, at the slow link), not the card's alone. The span of the update on the card in the
  threads' form is not recorded.
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
```
