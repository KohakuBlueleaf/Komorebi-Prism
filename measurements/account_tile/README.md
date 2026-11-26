# The account of a frame with LIGHT shown

The presets `lit_tile` and `gi_tile`: `lit` and `gi` with the build option `light_shows`.
The last LIGHT command of a colour view (LIGHT, or its glass form with a glass layer)
converts the colour planes it holds for display on each tile's owner and writes the
display's pages; the SHOW command is not sent (`stages/direct/light/README.md`,
"Shown"). Each command of the frame accounted as in `measurements/account/`, whose
records are the stage-wise frames these are compared with.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz before and after every
  run as the runs report it.
- Date: 2026-11-26 (UTC+8), Komorebi 0.5.3 at e908d6d16; every record from one build of
  the tree.
- Each case: `scripts/run/account.py --pipeline P --scene S --view overview --size W H
  --frames 16 --card 1 --out measurements/account_tile/<record>`, P `lit_tile` or
  `gi_tile`: one load, 16 frames at the view's camera, Komorebi's trace of 1,024
  commands a core kept. Every number is the median over the 16 frames (a core's numbers
  core by core); every frame's code is 0.
- The pictures: each case's preset run with the stage-wise preset's check
  (`scripts/run/preset.py --pipeline P --check C`, C
  `prism.stages.direct.light.check.thread_frame.check` for `lit_tile`, the display
  stage's `prism.stages.post.show.check.check` for `gi_tile`, as `lit` and `gi` are
  recorded), 16 frames, and the stage-wise preset's run of the same case on the same
  build: the pushed pictures of frames 1 and 16 are the same bytes in every case (0 bytes
  different in 24 comparisons), and every check's report against the reference is the
  stage-wise one's. The display stage's check also compares the display with the
  frame's colour planes converted on the host; with LIGHT shown those planes are not
  written, so that comparison has no meaning for `gi_tile`.
- A control in a live run: `gi_tile` and `gi` on sponza, 1,024 x 1,024, the display's
  gamma set to 1.0 through the loop's control and back to 2.2: the pushed picture at
  each step is the same bytes in both presets (it differs from the loaded one at 1.0 and
  is the loaded one again at 2.2).

## What is here

| file | holds |
| --- | --- |
| `<scene>_overview_<W>_<H>_<pipeline>.json` | a case's record, as `measurements/account/`'s; LIGHT's shown command has a second CPU, `writer` (mover B): its busy steps `convert` and `write` (the display's writes with the waits for a scratch page's last write), its total their sum, its counts `show_rows` and `show_items`; its `moved` writes `display` in place of `planes` |

## The tile frame against the stage-wise frame

A row a case. Stage-wise: `measurements/account/`'s frame, the LIGHT command that shows
in the tile preset (LIGHT, or its glass form with a glass layer) and SHOW, in ms. Tile:
this page's frame and that LIGHT command (its growth over the stage-wise one). The
difference of the frames. LIGHT's mover B conversion over cores, mean / most, in ms.
LIGHT's standing still (the stage-wise command's in brackets).

| case | stage-wise frame | stage-wise LIGHT | SHOW | tile frame | tile LIGHT (growth) | frame difference | mover B conversion mean / most | LIGHT standing still |
| --- | ---: | --- | ---: | ---: | --- | --- | --- | --- |
| lit sponza 1024x1024 | 12.050 | light 1.748 | 0.798 | 11.348 | 1.843 (+0.095) | -0.702 (-5.8 %) | 0.708 / 0.756 | 0.257 (0.251) |
| lit bistro_interior 1024x1024 | 18.138 | light_glass 0.890 | 0.863 | 17.462 | 1.066 (+0.176) | -0.676 (-3.7 %) | 0.694 / 0.823 | 0.244 (0.407) |
| lit bistro_exterior 1024x1024 | 27.944 | light_glass 0.972 | 0.797 | 27.417 | 1.246 (+0.275) | -0.527 (-1.9 %) | 0.711 / 0.758 | 0.318 (0.369) |
| gi sponza 1024x1024 | 14.272 | light 3.993 | 0.793 | 13.568 | 4.081 (+0.088) | -0.704 (-4.9 %) | 0.702 / 0.751 | 0.470 (0.462) |
| gi bistro_interior 1024x1024 | 20.991 | light_glass 1.262 | 0.864 | 20.277 | 1.430 (+0.168) | -0.714 (-3.4 %) | 0.695 / 0.824 | 0.571 (0.739) |
| gi modern_hall 1024x1024 | 13.733 | light_glass 2.147 | 0.830 | 13.116 | 2.371 (+0.224) | -0.617 (-4.5 %) | 0.723 / 0.788 | 1.296 (1.410) |
| lit sponza 1920x1080 | 18.948 | light 3.099 | 1.542 | 17.492 | 3.185 (+0.085) | -1.456 (-7.7 %) | 1.407 / 1.496 | 0.285 (0.288) |
| lit bistro_interior 1920x1080 | 28.914 | light_glass 1.528 | 1.541 | 27.806 | 1.968 (+0.439) | -1.108 (-3.8 %) | 1.386 / 1.495 | 0.392 (0.631) |
| lit bistro_exterior 1920x1080 | 38.956 | light_glass 2.119 | 1.545 | 37.682 | 2.394 (+0.275) | -1.274 (-3.3 %) | 1.411 / 1.502 | 0.714 (1.035) |
| gi sponza 1920x1080 | 23.172 | light 7.331 | 1.527 | 21.751 | 7.436 (+0.105) | -1.421 (-6.1 %) | 1.395 / 1.483 | 0.570 (0.569) |
| gi bistro_interior 1920x1080 | 33.892 | light_glass 2.106 | 1.541 | 32.847 | 2.562 (+0.456) | -1.045 (-3.1 %) | 1.388 / 1.495 | 0.875 (1.103) |
| gi modern_hall 1920x1080 | 24.564 | light_glass 4.093 | 1.567 | 23.399 | 4.462 (+0.369) | -1.165 (-4.7 %) | 1.415 / 1.519 | 2.384 (2.596) |

Where the shown command is LIGHT's displayed form, it grows by 0.085 to 0.105 ms and
the frame is shorter by about SHOW's time less that growth. Where it is the glass form,
it grows by 0.168 to 0.456 ms, over the 0.1 ms the change was to stay within: mover B's
conversion (0.69 to 0.72 ms a core at 1,024 x 1,024, 1.39 to 1.42 ms at 1,920 x 1,080)
is longer than that form's pack thread on most cores (the writer's total over the pack
thread's on 31 to 100 of 120 cores). The pack thread's busy steps are what they were;
its wait `in` grows (`lit` bistro_interior 1,920 x 1,080: 0.068 to 0.541 ms mean,
busy 0.756 ms in both), and the command's closure falls to 0.84 to 0.95 with mover B's
time untimed by the pack CPU's profile (the case tables' `light_glass` rows).

## The tables

As in `measurements/account/`: a case a table, a row a command.

### `lit_tile`, sponza, 1,024 x 1,024

Frame 11.348 ms (the preset's run 11.342 ms, +0.05 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.669 | writer | 0.194 / 0.357 | pack 0.150 | 0.305 | 16.38 (24.5) | 0.98 (1.5) | 0.972 | untimed 0.012 |
| sum.opaque | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.6) | 0.50 (8.9) | 0.940 | outside 0.003 |
| middle.opaque | 0.435 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.092 | writer | 0.068 / 0.086 | 0 | 0.019 | 2.95 (32.1) | 0.64 (6.9) | 0.944 | outside 0.004 |
| setup.opaque | 0.865 | pack | 0.485 / 0.696 | mail 0.018, out 0.013 | 0.262 | 16.38 (18.9) | 27.87 (32.2) | 0.905 | cpu_other 0.069 |
| fill.opaque | 1.490 | writer | 0.006 / 0.006 | planes 1.411 | 0.062 | 28.12 (18.9) | 20.97 (14.1) | 0.992 | cpu_other 0.006 |
| count.masked | 0.108 | writer | 0.079 / 0.086 | pack 0.001 | 0.010 | 2.52 (23.3) | 0.98 (9.1) | 0.828 | untimed 0.011 |
| sum.masked | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.6) | 0.50 (9.0) | 0.940 | outside 0.003 |
| hist.masked | 0.027 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.52 (19.5) | 0.808 | outside 0.003 |
| hsum.masked | 0.071 | (trace) | 0.038 / - | - | 0.029 | 0.52 (7.4) | 1.05 (14.9) | 0.952 | outside 0.003 |
| middle.masked | 0.708 | thread | - | - | - | - | - | - | - |
| place.masked | 0.097 | writer | 0.073 / 0.091 | 0 | 0.019 | 2.95 (30.4) | 0.55 (5.7) | 0.947 | outside 0.004 |
| setup.masked | 0.223 | pack | 0.081 / 0.091 | mail 0.003, out 0.001 | 0.025 | 2.52 (11.3) | 5.78 (25.9) | 0.496 | cpu_other 0.096 |
| fill.masked | 0.162 | writer | 0.032 / 0.059 | planes 0.107 | 0.011 | 5.95 (36.7) | 20.97 (129.3) | 0.925 | cpu_other 0.006 |
| shade.opaque | 3.373 | pack | 2.575 / 3.252 | in 0.021, pages 0.028 | 0.692 | 218.55 (64.8) | 45.82 (13.6) | 0.983 | cpu_other 0.052 |
| shade.masked | 0.783 | pack | 0.243 / 0.672 | in 0.026, pages 0.003 | 0.454 | 47.39 (60.6) | 4.33 (5.5) | 0.929 | cpu_other 0.050 |
| light | 1.843 | pack | 1.412 / 1.653 | in 0.015, pages 0.030 | 0.257 | 102.03 (55.4) | 4.19 (2.3) | 0.930 | untimed 0.084 |
| push | 0.287 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.6) | 0.002 | push 0.283 |

### `lit_tile`, bistro_interior, 1,024 x 1,024

Frame 17.462 ms (the preset's run 17.454 ms, +0.05 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 1.258 | writer | 0.294 / 0.685 | pack 0.436 | 0.506 | 56.18 (44.7) | 0.98 (0.8) | 0.983 | untimed 0.012 |
| sum.opaque | 0.055 | (trace) | 0.026 / - | - | 0.025 | 0.98 (17.8) | 0.50 (9.0) | 0.941 | outside 0.003 |
| hist.opaque | 0.028 | writer | 0.018 / 0.022 | 0 | 0.004 | 0.00 (0.0) | 0.71 (25.6) | 0.812 | outside 0.003 |
| hsum.opaque | 0.072 | (trace) | 0.053 / - | - | 0.016 | 0.71 (9.9) | 1.44 (19.9) | 0.953 | outside 0.003 |
| middle.opaque | 0.638 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.096 | writer | 0.072 / 0.090 | 0 | 0.019 | 2.95 (30.9) | 0.65 (6.8) | 0.946 | outside 0.004 |
| setup.opaque | 1.682 | pack | 1.225 / 1.504 | mail 0.058, out 0.023 | 0.291 | 56.18 (33.4) | 49.17 (29.2) | 0.946 | cpu_other 0.078 |
| fill.opaque | 1.773 | writer | 0.006 / 0.007 | planes 1.704 | 0.050 | 49.44 (27.9) | 20.97 (11.8) | 0.993 | cpu_other 0.007 |
| count.masked | 0.091 | writer | 0.061 / 0.067 | 0 | 0.011 | 1.44 (15.9) | 0.98 (10.8) | 0.798 | untimed 0.011 |
| sum.masked | 0.055 | (trace) | 0.026 / - | - | 0.025 | 0.98 (17.8) | 0.50 (9.1) | 0.940 | outside 0.003 |
| hist.masked | 0.025 | writer | 0.016 / 0.020 | 0 | 0.004 | 0.00 (0.0) | 0.28 (11.0) | 0.795 | outside 0.003 |
| hsum.masked | 0.070 | (trace) | 0.021 / - | - | 0.046 | 0.28 (4.0) | 0.56 (8.0) | 0.952 | outside 0.003 |
| middle.masked | 0.563 | thread | - | - | - | - | - | - | - |
| place.masked | 0.093 | writer | 0.070 / 0.087 | 0 | 0.019 | 2.95 (31.6) | 0.53 (5.6) | 0.946 | outside 0.004 |
| setup.masked | 0.169 | pack | 0.026 / 0.072 | mail 0.002 | 0.040 | 1.44 (8.5) | 0.77 (4.6) | 0.403 | cpu_other 0.090 |
| fill.masked | 0.143 | writer | 0.034 / 0.075 | planes 0.008 | 0.033 | 0.92 (6.4) | 20.97 (146.5) | 0.524 | outside 0.059 |
| count.glass | 0.389 | writer | 0.133 / 0.160 | pack 0.120 | 0.117 | 15.91 (40.9) | 0.98 (2.5) | 0.951 | untimed 0.012 |
| sum.glass | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.7) | 0.50 (9.0) | 0.940 | outside 0.003 |
| hist.glass | 0.026 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.45 (17.2) | 0.807 | outside 0.003 |
| hsum.glass | 0.070 | (trace) | 0.033 / - | - | 0.034 | 0.45 (6.4) | 0.91 (13.0) | 0.951 | outside 0.003 |
| middle.glass | 0.678 | thread | - | - | - | - | - | - | - |
| place.glass | 0.097 | writer | 0.073 / 0.091 | 0 | 0.019 | 2.95 (30.5) | 0.55 (5.7) | 0.947 | outside 0.004 |
| setup.glass | 0.508 | pack | 0.350 / 0.397 | mail 0.017, out 0.003 | 0.032 | 15.91 (31.3) | 16.95 (33.3) | 0.790 | cpu_other 0.093 |
| fill.glass | 0.438 | writer | 0.020 / 0.047 | planes 0.350 | 0.056 | 17.14 (39.1) | 20.97 (47.9) | 0.971 | cpu_other 0.007 |
| shade.opaque | 3.650 | pack | 2.570 / 3.552 | in 0.023, pages 0.015 | 0.986 | 152.35 (41.7) | 45.69 (12.5) | 0.985 | cpu_other 0.051 |
| shade.masked | 0.300 | pack | 0.062 / 0.237 | in 0.017, pages 0.001 | 0.161 | 13.71 (45.7) | 1.54 (5.1) | 0.806 | cpu_other 0.053 |
| shade.glass | 0.708 | pack | 0.261 / 0.615 | in 0.022 | 0.371 | 24.55 (34.7) | 4.24 (6.0) | 0.923 | cpu_other 0.049 |
| light | 2.373 | pack | 1.920 / 2.275 | in 0.017, pages 0.031 | 0.364 | 108.35 (45.7) | 12.58 (5.3) | 0.982 | cpu_other 0.037 |
| light_glass | 1.066 | writer | 0.695 / 0.824 | 0 | 0.244 | 121.12 (113.6) | 4.19 (3.9) | 0.878 | untimed 0.112 |
| push | 0.287 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.6) | 0.002 | push 0.283 |

### `lit_tile`, bistro_exterior, 1,024 x 1,024

Frame 27.417 ms (the preset's run 27.411 ms, +0.02 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 2.499 | writer | 0.365 / 1.013 | pack 1.317 | 0.793 | 148.63 (59.5) | 0.98 (0.4) | 0.989 | untimed 0.012 |
| sum.opaque | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.6) | 0.50 (8.9) | 0.940 | outside 0.003 |
| middle.opaque | 0.433 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.092 | writer | 0.068 / 0.086 | 0 | 0.019 | 2.95 (32.0) | 0.64 (6.9) | 0.945 | outside 0.004 |
| setup.opaque | 2.882 | pack | 2.465 / 2.700 | mail 0.154, out 0.019 | 0.164 | 148.63 (51.6) | 58.38 (20.3) | 0.972 | cpu_other 0.071 |
| fill.opaque | 2.640 | writer | 0.006 / 0.007 | planes 2.491 | 0.131 | 58.63 (22.2) | 20.97 (7.9) | 0.995 | cpu_other 0.007 |
| count.masked | 0.851 | pack | 0.468 / 0.808 | mail 0.034 | 0.257 | 55.11 (64.7) | 0.98 (1.2) | 0.974 | cpu_other 0.008 |
| sum.masked | 0.056 | (trace) | 0.026 / - | - | 0.027 | 0.98 (17.4) | 0.50 (8.9) | 0.940 | outside 0.003 |
| hist.masked | 0.026 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.56 (21.3) | 0.804 | outside 0.003 |
| hsum.masked | 0.071 | (trace) | 0.041 / - | - | 0.026 | 0.56 (7.9) | 1.13 (16.0) | 0.952 | outside 0.003 |
| middle.masked | 0.711 | thread | - | - | - | - | - | - | - |
| place.masked | 0.097 | writer | 0.074 / 0.091 | 0 | 0.019 | 2.95 (30.3) | 0.59 (6.1) | 0.947 | outside 0.004 |
| setup.masked | 1.916 | pack | 0.893 / 1.672 | mail 0.057, out 0.116 | 0.837 | 55.11 (28.8) | 64.74 (33.8) | 0.944 | cpu_other 0.092 |
| fill.masked | 1.908 | writer | 0.010 / 0.035 | planes 1.720 | 0.165 | 64.94 (34.0) | 20.97 (11.0) | 0.993 | cpu_other 0.008 |
| count.glass | 0.088 | writer | 0.059 / 0.068 | 0 | 0.011 | 0.28 (3.2) | 0.98 (11.2) | 0.797 | untimed 0.011 |
| sum.glass | 0.055 | (trace) | 0.026 / - | - | 0.025 | 0.98 (17.8) | 0.50 (9.1) | 0.939 | outside 0.003 |
| hist.glass | 0.026 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.51 (19.7) | 0.803 | outside 0.003 |
| hsum.glass | 0.071 | (trace) | 0.038 / - | - | 0.029 | 0.51 (7.3) | 1.04 (14.7) | 0.952 | outside 0.003 |
| middle.glass | 0.577 | thread | - | - | - | - | - | - | - |
| place.glass | 0.094 | writer | 0.070 / 0.088 | 0 | 0.019 | 2.95 (31.5) | 0.56 (6.0) | 0.945 | outside 0.004 |
| setup.glass | 0.155 | pack | 0.008 / 0.074 | mail 0.001 | 0.048 | 0.28 (1.8) | 0.65 (4.2) | 0.373 | cpu_other 0.087 |
| fill.glass | 0.130 | writer | 0.028 / 0.068 | planes 0.028 | 0.015 | 0.83 (6.4) | 20.97 (161.2) | 0.548 | outside 0.050 |
| shade.opaque | 5.734 | pack | 4.239 / 5.621 | in 0.021, pages 0.021 | 1.395 | 222.60 (38.8) | 45.78 (8.0) | 0.990 | cpu_other 0.050 |
| shade.masked | 2.372 | pack | 1.104 / 2.267 | in 0.025, pages 0.006 | 1.179 | 137.76 (58.1) | 18.38 (7.8) | 0.976 | cpu_other 0.052 |
| shade.glass | 0.763 | pack | 0.506 / 0.694 | in 0.012, pages 0.001 | 0.187 | 10.70 (14.0) | 15.59 (20.4) | 0.927 | cpu_other 0.050 |
| light | 1.574 | pack | 1.314 / 1.494 | in 0.015, pages 0.030 | 0.175 | 95.01 (60.4) | 12.58 (8.0) | 0.974 | cpu_other 0.035 |
| light_glass | 1.246 | pack | 0.507 / 0.851 | in 0.152, pages 0.009 | 0.318 | 89.76 (72.0) | 4.19 (3.4) | 0.842 | untimed 0.142 |
| push | 0.287 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.6) | 0.002 | push 0.283 |

### `gi_tile`, sponza, 1,024 x 1,024

Frame 13.568 ms (the preset's run 13.566 ms, +0.01 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.656 | writer | 0.189 / 0.344 | pack 0.151 | 0.298 | 16.38 (25.0) | 0.98 (1.5) | 0.971 | untimed 0.012 |
| sum.opaque | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.7) | 0.50 (9.0) | 0.941 | outside 0.003 |
| middle.opaque | 0.432 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.091 | writer | 0.066 / 0.085 | 0 | 0.019 | 2.95 (32.5) | 0.64 (7.0) | 0.943 | outside 0.004 |
| setup.opaque | 0.863 | pack | 0.484 / 0.696 | mail 0.018, out 0.013 | 0.261 | 16.38 (19.0) | 27.87 (32.3) | 0.904 | cpu_other 0.070 |
| fill.opaque | 1.490 | writer | 0.006 / 0.006 | planes 1.411 | 0.062 | 28.12 (18.9) | 20.97 (14.1) | 0.992 | cpu_other 0.006 |
| count.masked | 0.107 | writer | 0.078 / 0.085 | pack 0.001 | 0.009 | 2.52 (23.6) | 0.98 (9.2) | 0.826 | untimed 0.011 |
| sum.masked | 0.055 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.7) | 0.50 (9.0) | 0.940 | outside 0.003 |
| hist.masked | 0.027 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.52 (19.2) | 0.802 | outside 0.003 |
| hsum.masked | 0.071 | (trace) | 0.038 / - | - | 0.029 | 0.52 (7.4) | 1.05 (14.9) | 0.951 | outside 0.003 |
| middle.masked | 0.708 | thread | - | - | - | - | - | - | - |
| place.masked | 0.095 | writer | 0.071 / 0.089 | 0 | 0.019 | 2.95 (31.0) | 0.55 (5.8) | 0.945 | outside 0.004 |
| setup.masked | 0.224 | pack | 0.081 / 0.091 | mail 0.003, out 0.001 | 0.025 | 2.52 (11.3) | 5.78 (25.8) | 0.495 | cpu_other 0.096 |
| fill.masked | 0.162 | writer | 0.032 / 0.059 | planes 0.107 | 0.011 | 5.95 (36.6) | 20.97 (129.1) | 0.925 | cpu_other 0.006 |
| shade.opaque | 3.378 | pack | 2.577 / 3.255 | in 0.021, pages 0.028 | 0.694 | 218.55 (64.7) | 45.82 (13.6) | 0.983 | cpu_other 0.052 |
| shade.masked | 0.783 | pack | 0.243 / 0.672 | in 0.026, pages 0.003 | 0.454 | 47.39 (60.6) | 4.33 (5.5) | 0.929 | cpu_other 0.050 |
| light | 4.081 | pack | 3.401 / 3.850 | in 0.014, pages 0.030, field_pages 0.029 | 0.470 | 147.45 (36.1) | 4.19 (1.0) | 0.966 | untimed 0.083 |
| push | 0.286 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.7) | 0.002 | push 0.282 |

### `gi_tile`, bistro_interior, 1,024 x 1,024

Frame 20.277 ms (the preset's run 20.277 ms, +0.00 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 1.257 | writer | 0.285 / 0.654 | pack 0.441 | 0.510 | 56.18 (44.7) | 0.98 (0.8) | 0.983 | untimed 0.012 |
| sum.opaque | 0.055 | (trace) | 0.026 / - | - | 0.025 | 0.98 (17.7) | 0.50 (9.0) | 0.939 | outside 0.003 |
| hist.opaque | 0.028 | writer | 0.018 / 0.022 | 0 | 0.004 | 0.00 (0.0) | 0.71 (25.6) | 0.809 | outside 0.003 |
| hsum.opaque | 0.072 | (trace) | 0.053 / - | - | 0.016 | 0.71 (9.9) | 1.44 (19.9) | 0.953 | outside 0.003 |
| middle.opaque | 0.636 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.093 | writer | 0.069 / 0.087 | 0 | 0.019 | 2.95 (31.7) | 0.65 (7.0) | 0.945 | outside 0.004 |
| setup.opaque | 1.681 | pack | 1.224 / 1.503 | mail 0.058, out 0.023 | 0.291 | 56.18 (33.4) | 49.17 (29.2) | 0.946 | cpu_other 0.078 |
| fill.opaque | 1.773 | writer | 0.006 / 0.007 | planes 1.704 | 0.050 | 49.44 (27.9) | 20.97 (11.8) | 0.993 | cpu_other 0.007 |
| count.masked | 0.091 | writer | 0.061 / 0.066 | 0 | 0.011 | 1.44 (15.9) | 0.98 (10.8) | 0.798 | untimed 0.011 |
| sum.masked | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.6) | 0.50 (9.0) | 0.940 | outside 0.003 |
| hist.masked | 0.025 | writer | 0.016 / 0.020 | 0 | 0.004 | 0.00 (0.0) | 0.28 (10.9) | 0.796 | outside 0.003 |
| hsum.masked | 0.070 | (trace) | 0.021 / - | - | 0.046 | 0.28 (4.0) | 0.56 (8.0) | 0.952 | outside 0.003 |
| middle.masked | 0.565 | thread | - | - | - | - | - | - | - |
| place.masked | 0.091 | writer | 0.067 / 0.085 | 0 | 0.019 | 2.95 (32.5) | 0.53 (5.8) | 0.943 | outside 0.004 |
| setup.masked | 0.169 | pack | 0.026 / 0.072 | mail 0.002 | 0.040 | 1.44 (8.5) | 0.77 (4.6) | 0.405 | cpu_other 0.090 |
| fill.masked | 0.143 | writer | 0.034 / 0.076 | planes 0.008 | 0.034 | 0.92 (6.4) | 20.97 (146.4) | 0.524 | outside 0.059 |
| count.glass | 0.389 | writer | 0.130 / 0.155 | pack 0.120 | 0.120 | 15.91 (40.9) | 0.98 (2.5) | 0.951 | untimed 0.012 |
| sum.glass | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.6) | 0.50 (9.0) | 0.941 | outside 0.003 |
| hist.glass | 0.026 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.45 (17.1) | 0.802 | outside 0.003 |
| hsum.glass | 0.070 | (trace) | 0.033 / - | - | 0.034 | 0.45 (6.4) | 0.91 (13.0) | 0.952 | outside 0.003 |
| middle.glass | 0.679 | thread | - | - | - | - | - | - | - |
| place.glass | 0.094 | writer | 0.070 / 0.088 | 0 | 0.019 | 2.95 (31.4) | 0.55 (5.9) | 0.945 | outside 0.004 |
| setup.glass | 0.509 | pack | 0.349 / 0.397 | mail 0.017, out 0.003 | 0.033 | 15.91 (31.3) | 16.95 (33.3) | 0.790 | cpu_other 0.093 |
| fill.glass | 0.438 | writer | 0.020 / 0.046 | planes 0.350 | 0.056 | 17.14 (39.1) | 20.97 (47.9) | 0.972 | cpu_other 0.007 |
| shade.opaque | 3.650 | pack | 2.570 / 3.551 | in 0.023, pages 0.015 | 0.984 | 152.35 (41.7) | 45.69 (12.5) | 0.985 | cpu_other 0.051 |
| shade.masked | 0.300 | pack | 0.062 / 0.237 | in 0.017, pages 0.001 | 0.161 | 13.71 (45.7) | 1.54 (5.1) | 0.806 | cpu_other 0.053 |
| shade.glass | 0.709 | pack | 0.261 / 0.615 | in 0.022 | 0.371 | 24.55 (34.6) | 4.24 (6.0) | 0.924 | cpu_other 0.049 |
| light | 4.845 | pack | 3.911 / 4.703 | in 0.016, pages 0.030, field_pages 0.030 | 0.807 | 164.08 (33.9) | 12.58 (2.6) | 0.990 | cpu_other 0.044 |
| light_glass | 1.430 | writer | 0.696 / 0.825 | 0 | 0.571 | 122.55 (85.7) | 4.19 (2.9) | 0.895 | untimed 0.118 |
| push | 0.286 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.7) | 0.002 | push 0.282 |

### `gi_tile`, modern_hall, 1,024 x 1,024

Frame 13.116 ms (the preset's run 13.118 ms, -0.01 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.155 | writer | 0.065 / 0.132 | 0 | 0.072 | 2.07 (13.4) | 0.98 (6.3) | 0.882 | untimed 0.012 |
| sum.opaque | 0.055 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.8) | 0.50 (9.0) | 0.940 | outside 0.003 |
| hist.opaque | 0.025 | writer | 0.016 / 0.020 | 0 | 0.004 | 0.00 (0.0) | 0.22 (8.6) | 0.788 | outside 0.003 |
| hsum.opaque | 0.070 | (trace) | 0.017 / - | - | 0.050 | 0.22 (3.1) | 0.43 (6.2) | 0.952 | outside 0.003 |
| middle.opaque | 0.509 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.090 | writer | 0.066 / 0.084 | 0 | 0.019 | 2.95 (32.6) | 0.64 (7.1) | 0.943 | outside 0.004 |
| setup.opaque | 0.248 | pack | 0.028 / 0.063 | mail 0.003 | 0.116 | 2.07 (8.3) | 2.41 (9.7) | 0.625 | cpu_other 0.079 |
| fill.opaque | 0.230 | writer | 0.007 / 0.012 | planes 0.200 | 0.011 | 2.68 (11.6) | 20.97 (91.3) | 0.948 | cpu_other 0.006 |
| count.glass | 0.111 | writer | 0.057 / 0.094 | 0 | 0.035 | 0.01 (0.1) | 0.98 (8.9) | 0.837 | untimed 0.011 |
| sum.glass | 0.055 | (trace) | 0.026 / - | - | 0.025 | 0.98 (17.9) | 0.50 (9.1) | 0.938 | outside 0.003 |
| middle.glass | 0.401 | thread | - | - | - | - | - | - | - |
| place.glass | 0.089 | writer | 0.065 / 0.083 | 0 | 0.019 | 2.95 (33.3) | 0.53 (5.9) | 0.942 | outside 0.004 |
| setup.glass | 0.162 | pack | 0.000 / 0.009 | mail 0.001 | 0.075 | 0.01 (0.1) | 0.12 (0.7) | 0.470 | cpu_other 0.079 |
| fill.glass | 0.125 | writer | 0.035 / 0.073 | planes 0.012 | 0.027 | 0.25 (2.0) | 20.97 (168.1) | 0.588 | outside 0.043 |
| shade.opaque | 1.801 | pack | 1.548 / 1.700 | in 0.022, pages 0.005 | 0.171 | 43.19 (24.0) | 46.14 (25.6) | 0.969 | cpu_other 0.050 |
| shade.glass | 0.406 | pack | 0.210 / 0.342 | in 0.009 | 0.134 | 3.32 (8.2) | 6.76 (16.6) | 0.873 | cpu_other 0.046 |
| light | 5.924 | pack | 5.049 / 5.795 | in 0.014, pages 0.029, field_pages 0.031 | 0.749 | 166.13 (28.0) | 12.58 (2.1) | 0.991 | cpu_other 0.046 |
| light_glass | 2.371 | writer | 0.723 / 0.789 | 0 | 1.296 | 80.95 (34.1) | 4.19 (1.8) | 0.930 | untimed 0.129 |
| push | 0.286 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.7) | 0.002 | push 0.282 |

### `lit_tile`, sponza, 1,920 x 1,080

Frame 17.492 ms (the preset's run 17.492 ms, +0.00 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.840 | writer | 0.261 / 0.643 | pack 0.054 | 0.504 | 16.38 (19.5) | 1.97 (2.3) | 0.976 | untimed 0.011 |
| sum.opaque | 0.115 | (trace) | 0.062 / - | - | 0.050 | 1.97 (17.1) | 1.00 (8.7) | 0.971 | outside 0.003 |
| middle.opaque | 0.867 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.168 | writer | 0.129 / 0.161 | 0 | 0.034 | 5.41 (32.2) | 0.77 (4.6) | 0.969 | outside 0.004 |
| setup.opaque | 1.325 | pack | 0.479 / 0.968 | mail 0.018, out 0.019 | 0.663 | 16.38 (12.4) | 34.21 (25.8) | 0.901 | cpu_other 0.116 |
| fill.opaque | 2.228 | writer | 0.011 / 0.012 | planes 2.107 | 0.098 | 34.59 (15.5) | 41.78 (18.8) | 0.995 | cpu_other 0.007 |
| count.masked | 0.161 | writer | 0.132 / 0.139 | 0 | 0.011 | 2.52 (15.7) | 1.97 (12.2) | 0.886 | untimed 0.011 |
| sum.masked | 0.114 | (trace) | 0.061 / - | - | 0.050 | 1.97 (17.2) | 1.00 (8.7) | 0.971 | outside 0.003 |
| hist.masked | 0.027 | writer | 0.018 / 0.022 | 0 | 0.004 | 0.00 (0.0) | 0.71 (26.1) | 0.799 | outside 0.003 |
| hsum.masked | 0.073 | (trace) | 0.053 / - | - | 0.017 | 0.71 (9.8) | 1.44 (19.8) | 0.953 | outside 0.003 |
| middle.masked | 1.156 | thread | - | - | - | - | - | - | - |
| place.masked | 0.171 | writer | 0.132 / 0.165 | 0 | 0.034 | 5.41 (31.6) | 0.55 (3.2) | 0.969 | outside 0.004 |
| setup.masked | 0.268 | pack | 0.069 / 0.079 | mail 0.003, out 0.001 | 0.034 | 2.52 (9.4) | 4.84 (18.1) | 0.400 | cpu_other 0.146 |
| fill.masked | 0.169 | writer | 0.074 / 0.131 | planes 0.062 | 0.011 | 5.01 (29.7) | 41.78 (247.5) | 0.873 | outside 0.012 |
| shade.opaque | 5.261 | pack | 4.502 / 5.155 | in 0.022, pages 0.035 | 0.643 | 272.65 (51.8) | 91.91 (17.5) | 0.989 | cpu_other 0.053 |
| shade.masked | 0.801 | pack | 0.342 / 0.701 | in 0.024, pages 0.003 | 0.375 | 47.93 (59.8) | 6.98 (8.7) | 0.929 | cpu_other 0.051 |
| light | 3.185 | pack | 2.667 / 2.946 | in 0.027, pages 0.057 | 0.285 | 174.12 (54.7) | 8.36 (2.6) | 0.954 | untimed 0.084 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

### `lit_tile`, bistro_interior, 1,920 x 1,080

Frame 27.806 ms (the preset's run 27.802 ms, +0.01 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 1.507 | writer | 0.458 / 1.206 | pack 0.310 | 0.719 | 56.18 (37.3) | 1.97 (1.3) | 0.986 | untimed 0.013 |
| sum.opaque | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.8) | 0.971 | outside 0.003 |
| middle.opaque | 0.853 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.168 | writer | 0.129 / 0.162 | 0 | 0.034 | 5.41 (32.2) | 0.76 (4.5) | 0.969 | outside 0.004 |
| setup.opaque | 2.210 | pack | 1.469 / 1.954 | mail 0.058, out 0.037 | 0.528 | 56.18 (25.4) | 70.25 (31.8) | 0.942 | cpu_other 0.116 |
| fill.opaque | 3.274 | writer | 0.011 / 0.012 | planes 3.105 | 0.144 | 70.62 (21.6) | 41.78 (12.8) | 0.996 | cpu_other 0.008 |
| count.masked | 0.149 | writer | 0.119 / 0.125 | 0 | 0.011 | 1.44 (9.7) | 1.97 (13.2) | 0.876 | untimed 0.011 |
| sum.masked | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.3) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.masked | 0.025 | writer | 0.016 / 0.019 | 0 | 0.004 | 0.00 (0.0) | 0.43 (17.3) | 0.784 | outside 0.003 |
| hsum.masked | 0.070 | (trace) | 0.032 / - | - | 0.035 | 0.43 (6.1) | 0.87 (12.3) | 0.952 | outside 0.003 |
| middle.masked | 1.019 | thread | - | - | - | - | - | - | - |
| place.masked | 0.168 | writer | 0.130 / 0.162 | 0 | 0.034 | 5.41 (32.1) | 0.53 (3.2) | 0.969 | outside 0.004 |
| setup.masked | 0.234 | pack | 0.032 / 0.083 | mail 0.002 | 0.048 | 1.44 (6.1) | 1.32 (5.6) | 0.351 | cpu_other 0.140 |
| fill.masked | 0.164 | writer | 0.080 / 0.145 | planes 0.006 | 0.059 | 1.49 (9.1) | 41.78 (255.1) | 0.886 | outside 0.009 |
| count.glass | 0.463 | writer | 0.222 / 0.253 | pack 0.021 | 0.201 | 15.91 (34.4) | 1.97 (4.2) | 0.959 | untimed 0.012 |
| sum.glass | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.glass | 0.027 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.72 (26.9) | 0.796 | outside 0.003 |
| hsum.glass | 0.073 | (trace) | 0.053 / - | - | 0.016 | 0.72 (9.9) | 1.46 (20.0) | 0.953 | outside 0.003 |
| middle.glass | 1.151 | thread | - | - | - | - | - | - | - |
| place.glass | 0.172 | writer | 0.133 / 0.165 | 0 | 0.034 | 5.41 (31.5) | 0.57 (3.3) | 0.970 | outside 0.004 |
| setup.glass | 0.658 | pack | 0.437 / 0.485 | mail 0.017, out 0.004 | 0.042 | 15.91 (24.2) | 24.30 (36.9) | 0.759 | cpu_other 0.145 |
| fill.glass | 0.658 | writer | 0.020 / 0.057 | planes 0.576 | 0.048 | 24.49 (37.2) | 41.78 (63.5) | 0.981 | cpu_other 0.007 |
| shade.opaque | 6.194 | pack | 4.805 / 6.076 | in 0.024, pages 0.026 | 1.281 | 250.19 (40.4) | 89.26 (14.4) | 0.991 | cpu_other 0.052 |
| shade.masked | 0.522 | pack | 0.139 / 0.431 | in 0.021, pages 0.001 | 0.302 | 19.65 (37.6) | 3.50 (6.7) | 0.888 | cpu_other 0.053 |
| shade.glass | 0.912 | pack | 0.561 / 0.879 | in 0.023 | 0.273 | 34.80 (38.1) | 10.95 (12.0) | 0.940 | cpu_other 0.049 |
| light | 4.253 | pack | 3.764 / 4.098 | in 0.028, pages 0.059 | 0.344 | 186.56 (43.9) | 25.07 (5.9) | 0.986 | cpu_other 0.054 |
| light_glass | 1.968 | writer | 1.388 / 1.497 | 0 | 0.392 | 215.52 (109.5) | 8.36 (4.2) | 0.912 | untimed 0.128 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

### `lit_tile`, bistro_exterior, 1,920 x 1,080

Frame 37.682 ms (the preset's run 37.671 ms, +0.03 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 2.582 | writer | 0.469 / 1.585 | pack 1.222 | 0.866 | 148.63 (57.6) | 1.97 (0.8) | 0.989 | untimed 0.011 |
| sum.opaque | 0.114 | (trace) | 0.062 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.7) | 0.971 | outside 0.003 |
| middle.opaque | 0.864 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.168 | writer | 0.129 / 0.162 | 0 | 0.034 | 5.41 (32.2) | 0.77 (4.6) | 0.969 | outside 0.004 |
| setup.opaque | 3.207 | pack | 2.503 / 3.007 | mail 0.154, out 0.044 | 0.393 | 148.63 (46.3) | 76.90 (24.0) | 0.965 | cpu_other 0.102 |
| fill.opaque | 4.283 | writer | 0.011 / 0.012 | planes 4.090 | 0.168 | 77.29 (18.0) | 41.78 (9.8) | 0.997 | cpu_other 0.008 |
| count.masked | 0.873 | pack | 0.477 / 0.838 | mail 0.034, out 0.003 | 0.286 | 55.11 (63.1) | 1.97 (2.3) | 0.974 | cpu_other 0.009 |
| sum.masked | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.masked | 0.027 | writer | 0.017 / 0.022 | 0 | 0.004 | 0.00 (0.0) | 0.78 (28.8) | 0.798 | outside 0.003 |
| hsum.masked | 0.073 | (trace) | 0.058 / - | - | 0.012 | 0.78 (10.7) | 1.58 (21.5) | 0.953 | outside 0.003 |
| middle.masked | 1.200 | thread | - | - | - | - | - | - | - |
| place.masked | 0.173 | writer | 0.134 / 0.166 | 0 | 0.034 | 5.41 (31.3) | 0.61 (3.6) | 0.970 | outside 0.004 |
| setup.masked | 1.658 | pack | 0.854 / 1.373 | mail 0.057, out 0.093 | 0.573 | 55.11 (33.2) | 57.15 (34.5) | 0.906 | cpu_other 0.143 |
| fill.masked | 2.048 | writer | 0.036 / 0.080 | planes 1.872 | 0.126 | 57.38 (28.0) | 41.78 (20.4) | 0.993 | cpu_other 0.008 |
| count.glass | 0.147 | writer | 0.116 / 0.133 | 0 | 0.013 | 0.28 (1.9) | 1.97 (13.3) | 0.878 | untimed 0.011 |
| sum.glass | 0.114 | (trace) | 0.062 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.glass | 0.024 | writer | 0.015 / 0.018 | 0 | 0.004 | 0.00 (0.0) | 0.25 (10.3) | 0.777 | outside 0.003 |
| hsum.glass | 0.070 | (trace) | 0.019 / - | - | 0.048 | 0.25 (3.5) | 0.50 (7.1) | 0.952 | outside 0.003 |
| middle.glass | 0.972 | thread | - | - | - | - | - | - | - |
| place.glass | 0.167 | writer | 0.128 / 0.161 | 0 | 0.034 | 5.41 (32.3) | 0.59 (3.5) | 0.969 | outside 0.004 |
| setup.glass | 0.198 | pack | 0.008 / 0.076 | mail 0.001 | 0.044 | 0.28 (1.4) | 0.70 (3.5) | 0.270 | cpu_other 0.135 |
| fill.glass | 0.173 | writer | 0.071 / 0.139 | planes 0.025 | 0.064 | 0.93 (5.4) | 41.78 (241.6) | 0.930 | cpu_other 0.006 |
| shade.opaque | 8.832 | pack | 7.194 / 8.736 | in 0.022, pages 0.041 | 1.516 | 392.39 (44.4) | 91.91 (10.4) | 0.993 | cpu_other 0.053 |
| shade.masked | 2.629 | pack | 1.531 / 2.550 | in 0.023, pages 0.007 | 1.010 | 153.57 (58.4) | 28.80 (11.0) | 0.978 | cpu_other 0.052 |
| shade.glass | 1.120 | pack | 0.881 / 1.042 | in 0.014, pages 0.001 | 0.167 | 15.65 (14.0) | 27.44 (24.5) | 0.950 | cpu_other 0.051 |
| light | 2.877 | pack | 2.526 / 2.729 | in 0.027, pages 0.057 | 0.207 | 169.21 (58.8) | 25.07 (8.7) | 0.979 | cpu_other 0.054 |
| light_glass | 2.394 | pack | 0.958 / 1.925 | in 0.441, pages 0.015 | 0.714 | 162.48 (67.9) | 8.36 (3.5) | 0.906 | untimed 0.149 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

### `gi_tile`, sponza, 1,920 x 1,080

Frame 21.751 ms (the preset's run 21.747 ms, +0.02 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.823 | writer | 0.255 / 0.623 | pack 0.054 | 0.493 | 16.38 (19.9) | 1.97 (2.4) | 0.975 | untimed 0.011 |
| sum.opaque | 0.114 | (trace) | 0.062 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.8) | 0.971 | outside 0.003 |
| middle.opaque | 0.880 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.164 | writer | 0.125 / 0.157 | 0 | 0.035 | 5.41 (33.0) | 0.77 (4.7) | 0.968 | outside 0.004 |
| setup.opaque | 1.326 | pack | 0.478 / 0.968 | mail 0.018, out 0.019 | 0.663 | 16.38 (12.4) | 34.21 (25.8) | 0.901 | cpu_other 0.116 |
| fill.opaque | 2.228 | writer | 0.011 / 0.012 | planes 2.107 | 0.098 | 34.59 (15.5) | 41.78 (18.7) | 0.995 | cpu_other 0.007 |
| count.masked | 0.160 | writer | 0.131 / 0.138 | 0 | 0.011 | 2.52 (15.7) | 1.97 (12.3) | 0.885 | untimed 0.012 |
| sum.masked | 0.115 | (trace) | 0.061 / - | - | 0.050 | 1.97 (17.2) | 1.00 (8.7) | 0.971 | outside 0.003 |
| hist.masked | 0.028 | writer | 0.018 / 0.023 | 0 | 0.004 | 0.00 (0.0) | 0.71 (25.3) | 0.805 | outside 0.003 |
| hsum.masked | 0.073 | (trace) | 0.053 / - | - | 0.017 | 0.71 (9.8) | 1.44 (19.8) | 0.953 | outside 0.003 |
| middle.masked | 1.169 | thread | - | - | - | - | - | - | - |
| place.masked | 0.166 | writer | 0.127 / 0.160 | 0 | 0.034 | 5.41 (32.6) | 0.55 (3.3) | 0.969 | outside 0.004 |
| setup.masked | 0.268 | pack | 0.069 / 0.079 | mail 0.003, out 0.001 | 0.034 | 2.52 (9.4) | 4.84 (18.1) | 0.399 | cpu_other 0.146 |
| fill.masked | 0.170 | writer | 0.074 / 0.131 | planes 0.062 | 0.011 | 5.01 (29.5) | 41.78 (246.5) | 0.870 | outside 0.013 |
| shade.opaque | 5.261 | pack | 4.503 / 5.155 | in 0.022, pages 0.035 | 0.643 | 272.65 (51.8) | 91.91 (17.5) | 0.989 | cpu_other 0.053 |
| shade.masked | 0.801 | pack | 0.343 / 0.702 | in 0.024, pages 0.003 | 0.375 | 47.93 (59.8) | 6.98 (8.7) | 0.929 | cpu_other 0.051 |
| light | 7.436 | pack | 6.562 / 7.120 | in 0.027, pages 0.056, field_pages 0.056 | 0.570 | 253.19 (34.0) | 8.36 (1.1) | 0.978 | untimed 0.083 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

### `gi_tile`, bistro_interior, 1,920 x 1,080

Frame 32.847 ms (the preset's run 32.836 ms, +0.03 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 1.495 | writer | 0.446 / 1.157 | pack 0.318 | 0.711 | 56.18 (37.6) | 1.97 (1.3) | 0.986 | untimed 0.013 |
| sum.opaque | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.8) | 0.971 | outside 0.003 |
| middle.opaque | 0.872 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.164 | writer | 0.125 / 0.158 | 0 | 0.034 | 5.41 (33.0) | 0.76 (4.6) | 0.968 | outside 0.004 |
| setup.opaque | 2.209 | pack | 1.469 / 1.954 | mail 0.058, out 0.037 | 0.529 | 56.18 (25.4) | 70.25 (31.8) | 0.942 | cpu_other 0.116 |
| fill.opaque | 3.274 | writer | 0.011 / 0.012 | planes 3.105 | 0.144 | 70.62 (21.6) | 41.78 (12.8) | 0.996 | cpu_other 0.008 |
| count.masked | 0.148 | writer | 0.119 / 0.125 | 0 | 0.011 | 1.44 (9.7) | 1.97 (13.3) | 0.876 | untimed 0.011 |
| sum.masked | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.masked | 0.025 | writer | 0.016 / 0.019 | 0 | 0.004 | 0.00 (0.0) | 0.43 (17.1) | 0.785 | outside 0.003 |
| hsum.masked | 0.070 | (trace) | 0.032 / - | - | 0.035 | 0.43 (6.1) | 0.87 (12.3) | 0.951 | outside 0.003 |
| middle.masked | 1.033 | thread | - | - | - | - | - | - | - |
| place.masked | 0.164 | writer | 0.125 / 0.158 | 0 | 0.034 | 5.41 (33.0) | 0.53 (3.2) | 0.968 | outside 0.004 |
| setup.masked | 0.235 | pack | 0.032 / 0.083 | mail 0.002 | 0.048 | 1.44 (6.1) | 1.32 (5.6) | 0.351 | cpu_other 0.141 |
| fill.masked | 0.164 | writer | 0.079 / 0.145 | planes 0.006 | 0.059 | 1.49 (9.1) | 41.78 (254.8) | 0.883 | outside 0.010 |
| count.glass | 0.463 | writer | 0.218 / 0.248 | pack 0.021 | 0.204 | 15.91 (34.3) | 1.97 (4.2) | 0.959 | untimed 0.012 |
| sum.glass | 0.113 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.4) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.glass | 0.027 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.72 (26.7) | 0.798 | outside 0.003 |
| hsum.glass | 0.073 | (trace) | 0.053 / - | - | 0.016 | 0.72 (9.9) | 1.46 (20.0) | 0.953 | outside 0.003 |
| middle.glass | 1.160 | thread | - | - | - | - | - | - | - |
| place.glass | 0.167 | writer | 0.128 / 0.160 | 0 | 0.034 | 5.41 (32.4) | 0.57 (3.4) | 0.969 | outside 0.004 |
| setup.glass | 0.658 | pack | 0.437 / 0.485 | mail 0.017, out 0.004 | 0.042 | 15.91 (24.2) | 24.30 (36.9) | 0.759 | cpu_other 0.145 |
| fill.glass | 0.658 | writer | 0.020 / 0.058 | planes 0.576 | 0.049 | 24.49 (37.2) | 41.78 (63.5) | 0.981 | cpu_other 0.007 |
| shade.opaque | 6.195 | pack | 4.806 / 6.077 | in 0.024, pages 0.026 | 1.281 | 250.19 (40.4) | 89.26 (14.4) | 0.991 | cpu_other 0.052 |
| shade.masked | 0.522 | pack | 0.139 / 0.431 | in 0.021, pages 0.001 | 0.302 | 19.65 (37.6) | 3.50 (6.7) | 0.888 | cpu_other 0.053 |
| shade.glass | 0.913 | pack | 0.561 / 0.879 | in 0.023 | 0.273 | 34.80 (38.1) | 10.95 (12.0) | 0.940 | cpu_other 0.049 |
| light | 8.683 | pack | 7.733 / 8.446 | in 0.027, pages 0.058, field_pages 0.056 | 0.729 | 283.59 (32.7) | 25.07 (2.9) | 0.991 | cpu_other 0.075 |
| light_glass | 2.562 | pack | 0.870 / 1.964 | in 0.535, pages 0.012, field_pages 0.003 | 0.875 | 218.31 (85.2) | 8.36 (3.3) | 0.925 | untimed 0.134 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

### `gi_tile`, modern_hall, 1,920 x 1,080

Frame 23.399 ms (the preset's run 23.395 ms, +0.02 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.199 | writer | 0.126 / 0.174 | 0 | 0.054 | 2.07 (10.4) | 1.97 (9.9) | 0.908 | untimed 0.012 |
| sum.opaque | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.3) | 1.00 (8.8) | 0.971 | outside 0.003 |
| middle.opaque | 0.877 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.164 | writer | 0.125 / 0.157 | 0 | 0.034 | 5.41 (33.1) | 0.77 (4.7) | 0.968 | outside 0.004 |
| setup.opaque | 0.261 | pack | 0.030 / 0.052 | mail 0.003 | 0.072 | 2.07 (7.9) | 4.01 (15.4) | 0.463 | cpu_other 0.124 |
| fill.opaque | 0.454 | writer | 0.014 / 0.020 | planes 0.383 | 0.045 | 4.41 (9.7) | 41.78 (92.0) | 0.974 | cpu_other 0.006 |
| count.glass | 0.182 | writer | 0.114 / 0.158 | 0 | 0.049 | 0.01 (0.1) | 1.97 (10.8) | 0.901 | untimed 0.011 |
| sum.glass | 0.114 | (trace) | 0.061 / - | - | 0.050 | 1.97 (17.2) | 1.00 (8.7) | 0.971 | outside 0.003 |
| middle.glass | 0.817 | thread | - | - | - | - | - | - | - |
| place.glass | 0.161 | writer | 0.122 / 0.154 | 0 | 0.034 | 5.41 (33.7) | 0.54 (3.3) | 0.968 | outside 0.004 |
| setup.glass | 0.221 | pack | 0.000 / 0.008 | mail 0.001 | 0.082 | 0.01 (0.1) | 0.14 (0.6) | 0.377 | cpu_other 0.131 |
| fill.glass | 0.154 | writer | 0.081 / 0.142 | planes 0.005 | 0.055 | 0.25 (1.6) | 41.78 (270.9) | 0.922 | cpu_other 0.006 |
| shade.opaque | 3.384 | pack | 3.043 / 3.277 | in 0.021, pages 0.009 | 0.251 | 73.26 (21.6) | 91.91 (27.2) | 0.982 | cpu_other 0.054 |
| shade.glass | 0.421 | pack | 0.308 / 0.341 | in 0.010 | 0.050 | 4.75 (11.3) | 9.91 (23.6) | 0.876 | cpu_other 0.047 |
| light | 10.849 | pack | 9.855 / 10.610 | in 0.026, pages 0.056, field_pages 0.059 | 0.769 | 279.97 (25.8) | 25.07 (2.3) | 0.992 | cpu_other 0.079 |
| light_glass | 4.462 | pack | 1.377 / 3.903 | in 0.432, pages 0.008, field_pages 0.004 | 2.384 | 160.46 (36.0) | 8.36 (1.9) | 0.952 | untimed 0.148 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

## L1

The load's printed table a case, in bytes; `room` is what is left for them less the
total. A tile program holds 16,384 bytes more circular buffers than its stage-wise twin
(LIGHT's own field `shown_scratch`).

| case | circular buffers | control block and overlay area | slots: service (reader), 1 x 10,240 B (at most) | host transfer buffer | page bounds list | total | left for them | room |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lit_tile sponza 1024x1024 | 1,073,952 | 17,024 | 10,240 | 93,264 | 944 | 1,195,424 | 1,461,120 | 265,696 |
| lit_tile bistro_interior 1024x1024 | 1,073,952 | 17,024 | 10,240 | 93,264 | 1,472 | 1,195,952 | 1,300,416 | 104,464 |
| lit_tile bistro_exterior 1024x1024 | 1,073,952 | 17,024 | 10,240 | 93,264 | 1,472 | 1,195,952 | 1,300,416 | 104,464 |
| gi_tile sponza 1024x1024 | 1,104,288 | 17,024 | 10,240 | 32,848 | 1,008 | 1,165,408 | 1,300,416 | 135,008 |
| gi_tile bistro_interior 1024x1024 | 1,104,288 | 17,024 | 10,240 | 32,848 | 1,536 | 1,165,936 | 1,271,424 | 105,488 |
| gi_tile modern_hall 1024x1024 | 1,104,288 | 17,024 | 10,240 | 32,848 | 1,312 | 1,165,712 | 1,271,360 | 105,648 |
| lit_tile sponza 1920x1080 | 1,106,720 | 17,024 | 10,240 | 32,848 | 1,136 | 1,167,968 | 1,271,360 | 103,392 |
| lit_tile bistro_interior 1920x1080 | 1,106,720 | 17,024 | 10,240 | 32,848 | 1,808 | 1,168,640 | 1,271,360 | 102,720 |
| lit_tile bistro_exterior 1920x1080 | 1,106,720 | 17,024 | 10,240 | 32,848 | 1,808 | 1,168,640 | 1,271,360 | 102,720 |
| gi_tile sponza 1920x1080 | 1,137,056 | 17,024 | 10,240 | 32,848 | 1,200 | 1,198,368 | 1,271,360 | 72,992 |
| gi_tile bistro_interior 1920x1080 | 1,137,056 | 17,024 | 10,240 | 32,848 | 1,872 | 1,199,040 | 1,270,784 | 71,744 |
| gi_tile modern_hall 1920x1080 | 1,137,056 | 17,024 | 10,240 | 32,848 | 1,600 | 1,198,768 | 1,270,720 | 71,952 |

## Code sizes

Each kernel's ELF, in bytes.

| case | reader text / data / bss | writer text / data / bss | unpack text / data / bss | math text / data / bss | pack text / data / bss |
| --- | --- | --- | --- | --- | --- |
| lit_tile sponza 1024x1024 | 50,060 / 428 / 68 | 49,860 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,400 / 304 / 32 |
| lit_tile bistro_interior 1024x1024 | 50,060 / 428 / 68 | 49,860 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,400 / 304 / 32 |
| lit_tile bistro_exterior 1024x1024 | 50,060 / 428 / 68 | 49,860 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,400 / 304 / 32 |
| gi_tile sponza 1024x1024 | 49,088 / 536 / 68 | 53,976 / 488 / 100 | 23,500 / 592 / 36 | 12,088 / 200 / 32 | 117,396 / 312 / 56 |
| gi_tile bistro_interior 1024x1024 | 49,084 / 536 / 68 | 53,972 / 488 / 100 | 23,476 / 592 / 40 | 12,100 / 200 / 36 | 117,408 / 312 / 60 |
| gi_tile modern_hall 1024x1024 | 49,092 / 536 / 68 | 53,992 / 488 / 100 | 23,468 / 592 / 40 | 12,100 / 200 / 36 | 117,404 / 312 / 60 |
| lit_tile sponza 1920x1080 | 50,104 / 428 / 68 | 50,264 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,360 / 304 / 32 |
| lit_tile bistro_interior 1920x1080 | 50,104 / 428 / 68 | 50,264 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,360 / 304 / 32 |
| lit_tile bistro_exterior 1920x1080 | 50,104 / 428 / 68 | 50,264 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,360 / 304 / 32 |
| gi_tile sponza 1920x1080 | 49,288 / 536 / 68 | 54,212 / 488 / 100 | 23,500 / 592 / 36 | 12,088 / 200 / 32 | 117,604 / 312 / 56 |
| gi_tile bistro_interior 1920x1080 | 49,284 / 536 / 68 | 54,208 / 488 / 100 | 23,476 / 592 / 40 | 12,100 / 200 / 36 | 117,616 / 312 / 60 |
| gi_tile modern_hall 1920x1080 | 49,296 / 536 / 68 | 54,228 / 488 / 100 | 23,468 / 592 / 40 | 12,100 / 200 / 36 | 117,612 / 312 / 60 |
