# The account of a frame

What each command of a frame's time is made of: which CPU of a core is busy with what,
what it waits for, how many bytes move, and how long a core stands still after its own
work while the command waits for its slowest core. Each command of the director's
FRAME (each raster pass a layer, the middle pass, SHADE a layer, LIGHT, LIGHT's glass
form, SHOW, the push), from the stages' own profile pages and Komorebi's trace.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz before and after every
  run as the runs report it.
- Date: 2026-11-26 (UTC+8), Komorebi 0.5.3 at e908d6d16; every record from one build of
  the tree.
- Each case: `scripts/run/account.py --pipeline P --scene S --view overview --size W H
  --frames 16 --card 1`: one load, 16 frames at the view's camera, Komorebi's trace of
  1,024 commands a core kept (`--trace`, the loop's option `trace`). After each frame
  the host reads every profile page and each layer's directory; every number below is
  the median over the 16 frames (a core's numbers core by core). The pictures are not
  checked here; every frame's code is 0.
- The frame's times are those of `measurements/lit_frame/` and `measurements/gi_frame/`
  at the same case to within 0.03 % (each case's line below gives both), so no run with
  the trace off was made.
- The per-item constants: `scripts/run/account_fit.py` over the twelve records.

## What is here

| file | holds |
| --- | --- |
| `<scene>_overview_<W>_<H>_<pipeline>.json` | a case's record: `case` (pipeline, scene, view, size, frames, card, AICLK before and after, date, Komorebi's version and commit, the trace's commands, the layers); `codes`; `frames_traced` and `trace_frames` (each frame's first traced command and count); `frame_ms` (every times column's median, a layer unit's `<name>.<i>` by layer); `results` (the last row's result columns); `stages` (a record a command, below); `thread_ms`; `l1`; `code`; `closure` (each command's ratio) |
| `fit.json` | the per-item constants by `<pipeline>.<STAGE>`: over all scenes (`all`) and a scene each |

A command's record in `stages`:

| key | what it is |
| --- | --- |
| `command`, `layer` | the command's name (its times column) and its layer (none: the frame's once) |
| `command_ms` | the command's time in the times row: the director's timer around its submit and wait |
| `cores` | each CPU of a core whose profile page counts it: `busy` by step, `wait` by what it waited for, `total`, in ms, a list a core (none: the kernels keep no profile, or the thread's middle pass). `reader` is mover A (BRISC), `writer` mover B (NCRISC), `pack` the pack thread (TRISC 2). The steps and waits are the profile's own names: the passes' (`setup.h` `kSProf*`), FILL's (`raster.h`, `fill/walk.hpp`), SHADE's (`shade.h` `kShadeProf*`), LIGHT's (`light.h` `kLightProf*`), SHOW's (`show.h` `kShowProf*`). HIST and PLACE keep the writer's total alone; SUM, HSUM and the push keep none |
| `busy_from` | `profile`, or `trace` where there is no profile (then a core's busy is its take to its done) |
| `spread` | from the trace, after the command's first take on any core: the cores' done least, median and most, the last take, the leader's completion (`leader_sent`), and `standing_still`, the mean over cores of (most - own done), in ms |
| `terms_ms` | the command's time split, in ms, means over cores: `busy` and `waiting` (of a core's CPU with the longest total), `standing_still`, `take` (its take after the first), `cpu_other` (that CPU's total less its busy and waiting), `untimed` (its take to done less that total), `push` (the leader's completion after the last done), `outside` (the command's time less the leader's completion: the thread's submit, the event's way back); they add up to `command_ms` |
| `closure` | (busy + waiting + standing still) over `command_ms` |
| `moved` | bytes read and written over every core by kind (mesh, tables, lists, planes, texture pages, light pages, field pages, display), and each direction's sum as GB/s over `command_ms`. From the profiles' bytes and pages where they count them (COUNT's and SETUP's reader and writer bytes, FILL's reader pages, SHADE's texture pages, LIGHT's light and field pages, SHOW's rows), else from the frame's own tables: each core's directory items and their rows, the heavy tiles, the frame's tiles, the commands' words (SUM, HIST, HSUM, PLACE, FILL's and SHADE's planes, LIGHT's planes, the push) |
| `items` | the profile's counts a core (tiles, records, rows, pages, texels, passes, ...) and, for FILL, SHADE, LIGHT and SHOW, the walked directory's items and rows a core |

The rest of a record:

| key | what it is |
| --- | --- |
| `thread_ms` | the frame less the sum of its commands (the middle pass counted among them) |
| `l1` | `printed`: the L1 budget table the load printed (the build's, without the trace's pages), as rows of bytes, and the bytes left for them; `rows`: the same table as the loaded run holds it, with the trace's 16 bytes a command in its circular buffers |
| `code` | each kernel's ELF (`reader`, `writer`, `unpack`, `math`, `pack`): text, data and bss bytes (the toolchain's `size`), `handlers`: the bytes of the command switch's body charged to each handler's case by the line table (the bytes of out-of-line functions are not charged; the math kernel's switch is inlined into `kernel_main` and gives none), `functions`: its twelve largest functions (`nm --size-sort`) |

## The tables

A case a table, a row a command. `ms`: `command_ms`. `CPU`: the CPU with the longest
total on most cores, the one the closure takes (`(trace)`: no profile; `thread`: the
middle pass, no command on the cores). `busy mean / most`: over cores, its busy steps
summed (HIST, PLACE: the writer's total). `waiting`: its waits by kind, mean over cores
(those of 0.5 us or more). `standing still`: `spread.standing_still`. `read`, `written`:
`moved`'s sums in MB and GB/s. `closure`: the ratio. `not accounted, largest`: the
largest of `terms_ms`' take, cpu_other, untimed, push and outside, in ms.

### `lit`, sponza, 1,024 x 1,024

Frame 12.050 ms (committed 12.050 ms, 0.00 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.669 | writer | 0.193 / 0.356 | pack 0.151 | 0.307 | 16.38 (24.5) | 0.98 (1.5) | 0.973 | untimed 0.011 |
| sum.opaque | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.5) | 0.50 (8.9) | 0.941 | outside 0.003 |
| middle.opaque | 0.435 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.092 | writer | 0.068 / 0.086 | 0 | 0.019 | 2.95 (32.0) | 0.64 (6.9) | 0.943 | outside 0.004 |
| setup.opaque | 0.865 | pack | 0.485 / 0.696 | mail 0.018, out 0.013 | 0.262 | 16.38 (18.9) | 27.87 (32.2) | 0.905 | cpu_other 0.069 |
| fill.opaque | 1.490 | writer | 0.006 / 0.006 | planes 1.411 | 0.062 | 28.12 (18.9) | 20.97 (14.1) | 0.992 | cpu_other 0.006 |
| count.masked | 0.108 | writer | 0.079 / 0.085 | pack 0.001 | 0.010 | 2.52 (23.4) | 0.98 (9.1) | 0.828 | untimed 0.011 |
| sum.masked | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.6) | 0.50 (8.9) | 0.941 | outside 0.003 |
| hist.masked | 0.027 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.52 (19.6) | 0.807 | outside 0.003 |
| hsum.masked | 0.071 | (trace) | 0.038 / - | - | 0.029 | 0.52 (7.4) | 1.05 (14.9) | 0.951 | outside 0.003 |
| middle.masked | 0.709 | thread | - | - | - | - | - | - | - |
| place.masked | 0.097 | writer | 0.073 / 0.091 | 0 | 0.019 | 2.95 (30.4) | 0.55 (5.7) | 0.947 | outside 0.004 |
| setup.masked | 0.223 | pack | 0.081 / 0.091 | mail 0.003, out 0.001 | 0.025 | 2.52 (11.3) | 5.78 (25.9) | 0.496 | cpu_other 0.096 |
| fill.masked | 0.162 | writer | 0.032 / 0.059 | planes 0.107 | 0.011 | 5.95 (36.6) | 20.97 (129.2) | 0.926 | cpu_other 0.006 |
| shade.opaque | 3.377 | pack | 2.577 / 3.255 | in 0.021, pages 0.028 | 0.694 | 218.55 (64.7) | 45.82 (13.6) | 0.983 | cpu_other 0.051 |
| shade.masked | 0.782 | pack | 0.243 / 0.672 | in 0.027, pages 0.003 | 0.454 | 47.39 (60.6) | 4.33 (5.5) | 0.929 | cpu_other 0.050 |
| light | 1.748 | pack | 1.412 / 1.653 | in 0.015, pages 0.030 | 0.251 | 102.03 (58.4) | 12.58 (7.2) | 0.977 | cpu_other 0.035 |
| show | 0.798 | writer | 0.712 / 0.760 | planes 0.001 | 0.050 | 12.58 (15.8) | 4.19 (5.3) | 0.957 | cpu_other 0.029 |
| push | 0.286 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.7) | 0.002 | push 0.282 |

### `lit`, sponza, 1,920 x 1,080

Frame 18.948 ms (committed 18.952 ms, -0.02 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.840 | writer | 0.261 / 0.643 | pack 0.054 | 0.505 | 16.38 (19.5) | 1.97 (2.3) | 0.977 | untimed 0.010 |
| sum.opaque | 0.115 | (trace) | 0.062 / - | - | 0.050 | 1.97 (17.1) | 1.00 (8.7) | 0.971 | outside 0.003 |
| middle.opaque | 0.866 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.168 | writer | 0.129 / 0.162 | 0 | 0.034 | 5.41 (32.1) | 0.77 (4.6) | 0.969 | outside 0.004 |
| setup.opaque | 1.325 | pack | 0.479 / 0.968 | mail 0.018, out 0.019 | 0.662 | 16.38 (12.4) | 34.21 (25.8) | 0.901 | cpu_other 0.116 |
| fill.opaque | 2.228 | writer | 0.011 / 0.012 | planes 2.107 | 0.098 | 34.59 (15.5) | 41.78 (18.8) | 0.995 | cpu_other 0.007 |
| count.masked | 0.161 | writer | 0.132 / 0.139 | 0 | 0.010 | 2.52 (15.7) | 1.97 (12.2) | 0.886 | untimed 0.012 |
| sum.masked | 0.115 | (trace) | 0.061 / - | - | 0.050 | 1.97 (17.2) | 1.00 (8.7) | 0.971 | outside 0.003 |
| hist.masked | 0.027 | writer | 0.017 / 0.022 | 0 | 0.004 | 0.00 (0.0) | 0.71 (26.2) | 0.798 | outside 0.003 |
| hsum.masked | 0.073 | (trace) | 0.053 / - | - | 0.017 | 0.71 (9.8) | 1.44 (19.8) | 0.953 | outside 0.003 |
| middle.masked | 1.155 | thread | - | - | - | - | - | - | - |
| place.masked | 0.171 | writer | 0.132 / 0.165 | 0 | 0.034 | 5.41 (31.6) | 0.55 (3.2) | 0.970 | outside 0.004 |
| setup.masked | 0.268 | pack | 0.069 / 0.079 | mail 0.003, out 0.001 | 0.034 | 2.52 (9.4) | 4.84 (18.0) | 0.399 | cpu_other 0.146 |
| fill.masked | 0.169 | writer | 0.074 / 0.131 | planes 0.062 | 0.011 | 5.01 (29.7) | 41.78 (247.6) | 0.872 | outside 0.012 |
| shade.opaque | 5.260 | pack | 4.501 / 5.154 | in 0.022, pages 0.035 | 0.642 | 272.65 (51.8) | 91.91 (17.5) | 0.989 | cpu_other 0.053 |
| shade.masked | 0.801 | pack | 0.342 / 0.701 | in 0.024, pages 0.003 | 0.374 | 47.93 (59.8) | 6.98 (8.7) | 0.929 | cpu_other 0.052 |
| light | 3.099 | pack | 2.666 / 2.946 | in 0.027, pages 0.057 | 0.288 | 174.12 (56.2) | 25.07 (8.1) | 0.981 | cpu_other 0.055 |
| show | 1.542 | writer | 1.415 / 1.505 | planes 0.003 | 0.089 | 25.07 (16.3) | 8.36 (5.4) | 0.977 | cpu_other 0.030 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

### `lit`, bistro_interior, 1,024 x 1,024

Frame 18.138 ms (committed 18.136 ms, 0.01 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 1.257 | writer | 0.291 / 0.683 | pack 0.439 | 0.507 | 56.18 (44.7) | 0.98 (0.8) | 0.984 | untimed 0.011 |
| sum.opaque | 0.055 | (trace) | 0.026 / - | - | 0.025 | 0.98 (17.8) | 0.50 (9.1) | 0.940 | outside 0.003 |
| hist.opaque | 0.028 | writer | 0.018 / 0.022 | 0 | 0.004 | 0.00 (0.0) | 0.71 (25.7) | 0.813 | outside 0.003 |
| hsum.opaque | 0.072 | (trace) | 0.053 / - | - | 0.016 | 0.71 (9.9) | 1.44 (19.9) | 0.952 | outside 0.003 |
| middle.opaque | 0.636 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.096 | writer | 0.072 / 0.089 | 0 | 0.019 | 2.95 (30.9) | 0.65 (6.8) | 0.946 | outside 0.004 |
| setup.opaque | 1.681 | pack | 1.224 / 1.503 | mail 0.058, out 0.023 | 0.290 | 56.18 (33.4) | 49.17 (29.2) | 0.946 | cpu_other 0.078 |
| fill.opaque | 1.773 | writer | 0.006 / 0.007 | planes 1.704 | 0.050 | 49.44 (27.9) | 20.97 (11.8) | 0.993 | cpu_other 0.007 |
| count.masked | 0.091 | writer | 0.061 / 0.066 | 0 | 0.012 | 1.44 (15.8) | 0.98 (10.8) | 0.797 | untimed 0.011 |
| sum.masked | 0.055 | (trace) | 0.026 / - | - | 0.025 | 0.98 (17.8) | 0.50 (9.1) | 0.941 | outside 0.003 |
| hist.masked | 0.025 | writer | 0.016 / 0.020 | 0 | 0.004 | 0.00 (0.0) | 0.28 (10.9) | 0.797 | outside 0.003 |
| hsum.masked | 0.070 | (trace) | 0.021 / - | - | 0.046 | 0.28 (4.0) | 0.56 (8.0) | 0.951 | outside 0.003 |
| middle.masked | 0.561 | thread | - | - | - | - | - | - | - |
| place.masked | 0.093 | writer | 0.070 / 0.087 | 0 | 0.019 | 2.95 (31.6) | 0.53 (5.6) | 0.945 | outside 0.004 |
| setup.masked | 0.168 | pack | 0.026 / 0.072 | mail 0.002 | 0.038 | 1.44 (8.6) | 0.77 (4.6) | 0.400 | cpu_other 0.090 |
| fill.masked | 0.143 | writer | 0.034 / 0.075 | planes 0.008 | 0.033 | 0.92 (6.4) | 20.97 (146.4) | 0.521 | outside 0.059 |
| count.glass | 0.389 | writer | 0.132 / 0.158 | pack 0.120 | 0.118 | 15.91 (40.9) | 0.98 (2.5) | 0.951 | untimed 0.012 |
| sum.glass | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.6) | 0.50 (8.9) | 0.940 | outside 0.003 |
| hist.glass | 0.026 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.45 (17.2) | 0.805 | outside 0.003 |
| hsum.glass | 0.070 | (trace) | 0.033 / - | - | 0.034 | 0.45 (6.4) | 0.91 (13.0) | 0.950 | outside 0.003 |
| middle.glass | 0.678 | thread | - | - | - | - | - | - | - |
| place.glass | 0.097 | writer | 0.073 / 0.091 | 0 | 0.019 | 2.95 (30.5) | 0.55 (5.7) | 0.947 | outside 0.004 |
| setup.glass | 0.508 | pack | 0.349 / 0.397 | mail 0.017, out 0.003 | 0.031 | 15.91 (31.3) | 16.95 (33.4) | 0.789 | cpu_other 0.093 |
| fill.glass | 0.438 | writer | 0.020 / 0.047 | planes 0.350 | 0.056 | 17.14 (39.1) | 20.97 (47.9) | 0.972 | cpu_other 0.007 |
| shade.opaque | 3.652 | pack | 2.571 / 3.554 | in 0.023, pages 0.015 | 0.986 | 152.35 (41.7) | 45.69 (12.5) | 0.985 | cpu_other 0.051 |
| shade.masked | 0.300 | pack | 0.062 / 0.237 | in 0.017, pages 0.001 | 0.161 | 13.71 (45.7) | 1.54 (5.1) | 0.806 | cpu_other 0.053 |
| shade.glass | 0.709 | pack | 0.260 / 0.615 | in 0.022 | 0.371 | 24.55 (34.7) | 4.24 (6.0) | 0.923 | cpu_other 0.049 |
| light | 2.372 | pack | 1.918 / 2.274 | in 0.017, pages 0.031 | 0.364 | 108.35 (45.7) | 12.58 (5.3) | 0.983 | cpu_other 0.036 |
| light_glass | 0.890 | pack | 0.371 / 0.752 | in 0.052, pages 0.009 | 0.407 | 121.12 (136.0) | 12.58 (14.1) | 0.943 | cpu_other 0.046 |
| show | 0.863 | writer | 0.698 / 0.827 | planes 0.002 | 0.129 | 12.58 (14.6) | 4.19 (4.9) | 0.960 | cpu_other 0.029 |
| push | 0.286 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.7) | 0.002 | push 0.282 |

### `lit`, bistro_interior, 1,920 x 1,080

Frame 28.914 ms (committed 28.914 ms, -0.00 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 1.508 | writer | 0.458 / 1.206 | pack 0.310 | 0.720 | 56.18 (37.2) | 1.97 (1.3) | 0.987 | untimed 0.011 |
| sum.opaque | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.3) | 1.00 (8.8) | 0.971 | outside 0.003 |
| middle.opaque | 0.854 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.168 | writer | 0.129 / 0.161 | 0 | 0.034 | 5.41 (32.2) | 0.76 (4.5) | 0.969 | outside 0.004 |
| setup.opaque | 2.210 | pack | 1.470 / 1.954 | mail 0.058, out 0.037 | 0.528 | 56.18 (25.4) | 70.25 (31.8) | 0.942 | cpu_other 0.116 |
| fill.opaque | 3.274 | writer | 0.011 / 0.012 | planes 3.105 | 0.144 | 70.62 (21.6) | 41.78 (12.8) | 0.996 | cpu_other 0.008 |
| count.masked | 0.149 | writer | 0.119 / 0.125 | 0 | 0.011 | 1.44 (9.7) | 1.97 (13.2) | 0.877 | untimed 0.011 |
| sum.masked | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.3) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.masked | 0.025 | writer | 0.016 / 0.019 | 0 | 0.004 | 0.00 (0.0) | 0.43 (17.3) | 0.785 | outside 0.003 |
| hsum.masked | 0.070 | (trace) | 0.032 / - | - | 0.035 | 0.43 (6.1) | 0.87 (12.3) | 0.951 | outside 0.003 |
| middle.masked | 1.018 | thread | - | - | - | - | - | - | - |
| place.masked | 0.168 | writer | 0.130 / 0.162 | 0 | 0.034 | 5.41 (32.1) | 0.53 (3.2) | 0.969 | outside 0.004 |
| setup.masked | 0.234 | pack | 0.032 / 0.083 | mail 0.002 | 0.047 | 1.44 (6.2) | 1.32 (5.7) | 0.349 | cpu_other 0.140 |
| fill.masked | 0.164 | writer | 0.080 / 0.145 | planes 0.006 | 0.059 | 1.49 (9.1) | 41.78 (254.4) | 0.882 | outside 0.010 |
| count.glass | 0.464 | writer | 0.222 / 0.253 | pack 0.020 | 0.202 | 15.91 (34.3) | 1.97 (4.2) | 0.959 | untimed 0.012 |
| sum.glass | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.3) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.glass | 0.027 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.72 (26.9) | 0.795 | outside 0.003 |
| hsum.glass | 0.073 | (trace) | 0.053 / - | - | 0.016 | 0.72 (9.9) | 1.46 (20.0) | 0.953 | outside 0.003 |
| middle.glass | 1.150 | thread | - | - | - | - | - | - | - |
| place.glass | 0.172 | writer | 0.133 / 0.166 | 0 | 0.034 | 5.41 (31.5) | 0.57 (3.3) | 0.970 | outside 0.004 |
| setup.glass | 0.659 | pack | 0.437 / 0.484 | mail 0.017, out 0.004 | 0.042 | 15.91 (24.1) | 24.30 (36.9) | 0.759 | cpu_other 0.145 |
| fill.glass | 0.658 | writer | 0.020 / 0.058 | planes 0.576 | 0.049 | 24.49 (37.2) | 41.78 (63.5) | 0.981 | cpu_other 0.007 |
| shade.opaque | 6.196 | pack | 4.806 / 6.077 | in 0.024, pages 0.026 | 1.282 | 250.19 (40.4) | 89.26 (14.4) | 0.991 | cpu_other 0.052 |
| shade.masked | 0.522 | pack | 0.139 / 0.431 | in 0.021, pages 0.001 | 0.302 | 19.65 (37.6) | 3.50 (6.7) | 0.888 | cpu_other 0.053 |
| shade.glass | 0.912 | pack | 0.561 / 0.879 | in 0.023 | 0.273 | 34.80 (38.1) | 10.95 (12.0) | 0.940 | cpu_other 0.049 |
| light | 4.258 | pack | 3.767 / 4.101 | in 0.028, pages 0.059 | 0.344 | 186.56 (43.8) | 25.07 (5.9) | 0.986 | cpu_other 0.056 |
| light_glass | 1.528 | pack | 0.756 / 1.386 | in 0.068, pages 0.015 | 0.631 | 215.52 (141.0) | 25.07 (16.4) | 0.963 | cpu_other 0.051 |
| show | 1.541 | writer | 1.393 / 1.503 | planes 0.003 | 0.110 | 25.07 (16.3) | 8.36 (5.4) | 0.977 | cpu_other 0.030 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

### `lit`, bistro_exterior, 1,024 x 1,024

Frame 27.944 ms (committed 27.947 ms, -0.01 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 2.499 | writer | 0.362 / 1.005 | pack 1.322 | 0.792 | 148.63 (59.5) | 0.98 (0.4) | 0.990 | untimed 0.011 |
| sum.opaque | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.7) | 0.50 (9.0) | 0.940 | outside 0.003 |
| middle.opaque | 0.432 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.092 | writer | 0.068 / 0.086 | 0 | 0.019 | 2.95 (32.0) | 0.64 (6.9) | 0.944 | outside 0.004 |
| setup.opaque | 2.884 | pack | 2.465 / 2.698 | mail 0.154, out 0.019 | 0.164 | 148.63 (51.5) | 58.38 (20.2) | 0.972 | cpu_other 0.071 |
| fill.opaque | 2.640 | writer | 0.006 / 0.006 | planes 2.491 | 0.131 | 58.63 (22.2) | 20.97 (7.9) | 0.995 | cpu_other 0.007 |
| count.masked | 0.852 | pack | 0.469 / 0.809 | mail 0.034 | 0.257 | 55.11 (64.7) | 0.98 (1.2) | 0.974 | cpu_other 0.008 |
| sum.masked | 0.055 | (trace) | 0.026 / - | - | 0.025 | 0.98 (17.8) | 0.50 (9.0) | 0.940 | outside 0.003 |
| hist.masked | 0.026 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.56 (21.3) | 0.801 | outside 0.003 |
| hsum.masked | 0.071 | (trace) | 0.041 / - | - | 0.026 | 0.56 (7.9) | 1.13 (16.0) | 0.951 | outside 0.003 |
| middle.masked | 0.712 | thread | - | - | - | - | - | - | - |
| place.masked | 0.097 | writer | 0.074 / 0.091 | 0 | 0.019 | 2.95 (30.3) | 0.59 (6.1) | 0.947 | outside 0.004 |
| setup.masked | 1.916 | pack | 0.893 / 1.672 | mail 0.057, out 0.117 | 0.837 | 55.11 (28.8) | 64.74 (33.8) | 0.944 | cpu_other 0.092 |
| fill.masked | 1.908 | writer | 0.010 / 0.035 | planes 1.720 | 0.165 | 64.94 (34.0) | 20.97 (11.0) | 0.993 | cpu_other 0.008 |
| count.glass | 0.088 | writer | 0.059 / 0.068 | 0 | 0.011 | 0.28 (3.2) | 0.98 (11.1) | 0.795 | untimed 0.011 |
| sum.glass | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.6) | 0.50 (9.0) | 0.941 | outside 0.003 |
| hist.glass | 0.026 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.51 (19.8) | 0.799 | outside 0.003 |
| hsum.glass | 0.071 | (trace) | 0.038 / - | - | 0.029 | 0.51 (7.3) | 1.04 (14.7) | 0.951 | outside 0.003 |
| middle.glass | 0.580 | thread | - | - | - | - | - | - | - |
| place.glass | 0.094 | writer | 0.070 / 0.087 | 0 | 0.019 | 2.95 (31.5) | 0.56 (6.0) | 0.945 | outside 0.004 |
| setup.glass | 0.155 | pack | 0.008 / 0.073 | mail 0.001 | 0.049 | 0.28 (1.8) | 0.65 (4.2) | 0.374 | cpu_other 0.088 |
| fill.glass | 0.130 | writer | 0.028 / 0.066 | planes 0.028 | 0.016 | 0.83 (6.4) | 20.97 (161.4) | 0.551 | outside 0.049 |
| shade.opaque | 5.738 | pack | 4.243 / 5.626 | in 0.022, pages 0.021 | 1.397 | 222.60 (38.8) | 45.78 (8.0) | 0.990 | cpu_other 0.050 |
| shade.masked | 2.372 | pack | 1.104 / 2.267 | in 0.025, pages 0.006 | 1.180 | 137.76 (58.1) | 18.38 (7.7) | 0.976 | cpu_other 0.052 |
| shade.glass | 0.762 | pack | 0.506 / 0.694 | in 0.012, pages 0.001 | 0.187 | 10.70 (14.0) | 15.59 (20.5) | 0.927 | cpu_other 0.050 |
| light | 1.574 | pack | 1.314 / 1.494 | in 0.015, pages 0.030 | 0.175 | 95.01 (60.4) | 12.58 (8.0) | 0.974 | cpu_other 0.035 |
| light_glass | 0.972 | pack | 0.507 / 0.851 | in 0.034, pages 0.009 | 0.369 | 89.76 (92.4) | 12.58 (13.0) | 0.947 | cpu_other 0.047 |
| show | 0.797 | writer | 0.714 / 0.761 | planes 0.001 | 0.046 | 12.58 (15.8) | 4.19 (5.3) | 0.956 | cpu_other 0.029 |
| push | 0.286 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.7) | 0.002 | push 0.282 |

### `lit`, bistro_exterior, 1,920 x 1,080

Frame 38.956 ms (committed 38.958 ms, -0.00 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 2.586 | writer | 0.469 / 1.585 | pack 1.222 | 0.870 | 148.63 (57.5) | 1.97 (0.8) | 0.990 | cpu_other 0.011 |
| sum.opaque | 0.114 | (trace) | 0.062 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.7) | 0.971 | outside 0.003 |
| middle.opaque | 0.866 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.168 | writer | 0.129 / 0.162 | 0 | 0.034 | 5.41 (32.1) | 0.77 (4.6) | 0.969 | outside 0.004 |
| setup.opaque | 3.207 | pack | 2.502 / 3.008 | mail 0.154, out 0.044 | 0.393 | 148.63 (46.4) | 76.90 (24.0) | 0.966 | cpu_other 0.102 |
| fill.opaque | 4.282 | writer | 0.011 / 0.012 | planes 4.090 | 0.168 | 77.29 (18.0) | 41.78 (9.8) | 0.997 | cpu_other 0.008 |
| count.masked | 0.874 | pack | 0.476 / 0.839 | mail 0.034, out 0.003 | 0.286 | 55.11 (63.1) | 1.97 (2.3) | 0.974 | cpu_other 0.009 |
| sum.masked | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.masked | 0.027 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.78 (28.8) | 0.798 | outside 0.003 |
| hsum.masked | 0.074 | (trace) | 0.058 / - | - | 0.012 | 0.78 (10.6) | 1.58 (21.4) | 0.953 | outside 0.003 |
| middle.masked | 1.199 | thread | - | - | - | - | - | - | - |
| place.masked | 0.173 | writer | 0.134 / 0.167 | 0 | 0.034 | 5.41 (31.3) | 0.61 (3.6) | 0.970 | outside 0.004 |
| setup.masked | 1.659 | pack | 0.853 / 1.374 | mail 0.057, out 0.093 | 0.574 | 55.11 (33.2) | 57.15 (34.5) | 0.906 | cpu_other 0.143 |
| fill.masked | 2.048 | writer | 0.036 / 0.080 | planes 1.872 | 0.126 | 57.38 (28.0) | 41.78 (20.4) | 0.993 | cpu_other 0.008 |
| count.glass | 0.147 | writer | 0.116 / 0.133 | 0 | 0.013 | 0.28 (1.9) | 1.97 (13.3) | 0.878 | untimed 0.011 |
| sum.glass | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.glass | 0.024 | writer | 0.014 / 0.018 | 0 | 0.004 | 0.00 (0.0) | 0.25 (10.3) | 0.778 | outside 0.003 |
| hsum.glass | 0.070 | (trace) | 0.019 / - | - | 0.048 | 0.25 (3.5) | 0.50 (7.1) | 0.952 | outside 0.003 |
| middle.glass | 0.973 | thread | - | - | - | - | - | - | - |
| place.glass | 0.167 | writer | 0.129 / 0.161 | 0 | 0.034 | 5.41 (32.3) | 0.59 (3.5) | 0.969 | outside 0.004 |
| setup.glass | 0.199 | pack | 0.008 / 0.076 | mail 0.001 | 0.044 | 0.28 (1.4) | 0.70 (3.5) | 0.273 | cpu_other 0.135 |
| fill.glass | 0.172 | writer | 0.071 / 0.138 | planes 0.025 | 0.064 | 0.93 (5.4) | 41.78 (242.6) | 0.930 | cpu_other 0.006 |
| shade.opaque | 8.831 | pack | 7.194 / 8.736 | in 0.022, pages 0.041 | 1.515 | 392.39 (44.4) | 91.91 (10.4) | 0.993 | cpu_other 0.053 |
| shade.masked | 2.628 | pack | 1.531 / 2.549 | in 0.022, pages 0.007 | 1.010 | 153.57 (58.4) | 28.80 (11.0) | 0.978 | cpu_other 0.051 |
| shade.glass | 1.119 | pack | 0.880 / 1.042 | in 0.015, pages 0.001 | 0.167 | 15.65 (14.0) | 27.44 (24.5) | 0.950 | cpu_other 0.051 |
| light | 2.877 | pack | 2.525 / 2.728 | in 0.027, pages 0.057 | 0.208 | 169.21 (58.8) | 25.07 (8.7) | 0.979 | cpu_other 0.055 |
| light_glass | 2.119 | pack | 0.959 / 1.927 | in 0.051, pages 0.015 | 1.035 | 162.48 (76.7) | 25.07 (11.8) | 0.972 | cpu_other 0.054 |
| show | 1.545 | writer | 1.418 / 1.510 | planes 0.003 | 0.089 | 25.07 (16.2) | 8.36 (5.4) | 0.977 | cpu_other 0.030 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

### `gi`, sponza, 1,024 x 1,024

Frame 14.272 ms (committed 14.267 ms, 0.03 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.657 | writer | 0.189 / 0.344 | pack 0.151 | 0.299 | 16.38 (24.9) | 0.98 (1.5) | 0.973 | untimed 0.011 |
| sum.opaque | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.6) | 0.50 (8.9) | 0.940 | outside 0.003 |
| middle.opaque | 0.433 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.091 | writer | 0.066 / 0.085 | 0 | 0.019 | 2.95 (32.5) | 0.64 (7.0) | 0.943 | outside 0.004 |
| setup.opaque | 0.864 | pack | 0.485 / 0.697 | mail 0.018, out 0.013 | 0.261 | 16.38 (18.9) | 27.87 (32.2) | 0.905 | cpu_other 0.069 |
| fill.opaque | 1.490 | writer | 0.006 / 0.006 | planes 1.411 | 0.062 | 28.12 (18.9) | 20.97 (14.1) | 0.992 | cpu_other 0.006 |
| count.masked | 0.107 | writer | 0.078 / 0.085 | pack 0.001 | 0.009 | 2.52 (23.5) | 0.98 (9.2) | 0.825 | untimed 0.011 |
| sum.masked | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.7) | 0.50 (9.0) | 0.940 | outside 0.003 |
| hist.masked | 0.027 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.52 (19.3) | 0.799 | outside 0.003 |
| hsum.masked | 0.071 | (trace) | 0.038 / - | - | 0.029 | 0.52 (7.4) | 1.05 (14.9) | 0.951 | outside 0.003 |
| middle.masked | 0.709 | thread | - | - | - | - | - | - | - |
| place.masked | 0.095 | writer | 0.071 / 0.089 | 0 | 0.019 | 2.95 (31.1) | 0.55 (5.8) | 0.945 | outside 0.004 |
| setup.masked | 0.224 | pack | 0.081 / 0.091 | mail 0.003, out 0.001 | 0.026 | 2.52 (11.3) | 5.78 (25.8) | 0.495 | cpu_other 0.096 |
| fill.masked | 0.162 | writer | 0.032 / 0.058 | planes 0.107 | 0.011 | 5.95 (36.7) | 20.97 (129.4) | 0.926 | cpu_other 0.006 |
| shade.opaque | 3.375 | pack | 2.575 / 3.253 | in 0.021, pages 0.028 | 0.693 | 218.55 (64.8) | 45.82 (13.6) | 0.983 | cpu_other 0.051 |
| shade.masked | 0.782 | pack | 0.243 / 0.672 | in 0.027, pages 0.003 | 0.453 | 47.39 (60.6) | 4.33 (5.5) | 0.929 | cpu_other 0.050 |
| light | 3.993 | pack | 3.408 / 3.857 | in 0.014, pages 0.030, field_pages 0.029 | 0.462 | 147.45 (36.9) | 12.58 (3.2) | 0.988 | cpu_other 0.045 |
| show | 0.793 | writer | 0.706 / 0.755 | planes 0.001 | 0.051 | 12.58 (15.9) | 4.19 (5.3) | 0.956 | cpu_other 0.029 |
| push | 0.286 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.7) | 0.002 | push 0.282 |

### `gi`, sponza, 1,920 x 1,080

Frame 23.172 ms (committed 23.177 ms, -0.02 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.823 | writer | 0.255 / 0.623 | pack 0.054 | 0.494 | 16.38 (19.9) | 1.97 (2.4) | 0.977 | untimed 0.010 |
| sum.opaque | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.7) | 0.971 | outside 0.003 |
| middle.opaque | 0.879 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.164 | writer | 0.125 / 0.157 | 0 | 0.035 | 5.41 (33.0) | 0.77 (4.7) | 0.968 | outside 0.004 |
| setup.opaque | 1.326 | pack | 0.478 / 0.968 | mail 0.018, out 0.019 | 0.664 | 16.38 (12.4) | 34.21 (25.8) | 0.901 | cpu_other 0.116 |
| fill.opaque | 2.228 | writer | 0.011 / 0.012 | planes 2.107 | 0.098 | 34.59 (15.5) | 41.78 (18.8) | 0.995 | cpu_other 0.007 |
| count.masked | 0.160 | writer | 0.131 / 0.138 | 0 | 0.010 | 2.52 (15.8) | 1.97 (12.3) | 0.885 | untimed 0.012 |
| sum.masked | 0.115 | (trace) | 0.062 / - | - | 0.050 | 1.97 (17.2) | 1.00 (8.7) | 0.971 | outside 0.003 |
| hist.masked | 0.028 | writer | 0.018 / 0.023 | 0 | 0.004 | 0.00 (0.0) | 0.71 (25.4) | 0.804 | outside 0.003 |
| hsum.masked | 0.073 | (trace) | 0.053 / - | - | 0.017 | 0.71 (9.8) | 1.44 (19.8) | 0.954 | outside 0.003 |
| middle.masked | 1.169 | thread | - | - | - | - | - | - | - |
| place.masked | 0.166 | writer | 0.127 / 0.160 | 0 | 0.034 | 5.41 (32.6) | 0.55 (3.3) | 0.968 | outside 0.004 |
| setup.masked | 0.268 | pack | 0.069 / 0.079 | mail 0.003, out 0.001 | 0.034 | 2.52 (9.4) | 4.84 (18.0) | 0.400 | cpu_other 0.146 |
| fill.masked | 0.169 | writer | 0.074 / 0.131 | planes 0.062 | 0.011 | 5.01 (29.6) | 41.78 (246.7) | 0.868 | outside 0.013 |
| shade.opaque | 5.261 | pack | 4.502 / 5.155 | in 0.022, pages 0.035 | 0.643 | 272.65 (51.8) | 91.91 (17.5) | 0.989 | cpu_other 0.053 |
| shade.masked | 0.801 | pack | 0.343 / 0.701 | in 0.024, pages 0.003 | 0.375 | 47.93 (59.8) | 6.98 (8.7) | 0.929 | cpu_other 0.051 |
| light | 7.331 | pack | 6.545 / 7.101 | in 0.027, pages 0.056, field_pages 0.056 | 0.569 | 253.19 (34.5) | 25.07 (3.4) | 0.990 | cpu_other 0.071 |
| show | 1.527 | writer | 1.402 / 1.491 | planes 0.003 | 0.087 | 25.07 (16.4) | 8.36 (5.5) | 0.977 | cpu_other 0.030 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

### `gi`, bistro_interior, 1,024 x 1,024

Frame 20.991 ms (committed 20.987 ms, 0.02 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 1.258 | writer | 0.285 / 0.654 | pack 0.444 | 0.509 | 56.18 (44.7) | 0.98 (0.8) | 0.984 | untimed 0.011 |
| sum.opaque | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.7) | 0.50 (9.0) | 0.942 | outside 0.003 |
| hist.opaque | 0.028 | writer | 0.018 / 0.022 | 0 | 0.004 | 0.00 (0.0) | 0.71 (25.6) | 0.812 | outside 0.003 |
| hsum.opaque | 0.072 | (trace) | 0.053 / - | - | 0.016 | 0.71 (9.9) | 1.44 (19.9) | 0.953 | outside 0.003 |
| middle.opaque | 0.634 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.093 | writer | 0.069 / 0.087 | 0 | 0.019 | 2.95 (31.7) | 0.65 (7.0) | 0.944 | outside 0.004 |
| setup.opaque | 1.682 | pack | 1.224 / 1.504 | mail 0.058, out 0.023 | 0.290 | 56.18 (33.4) | 49.17 (29.2) | 0.946 | cpu_other 0.078 |
| fill.opaque | 1.773 | writer | 0.006 / 0.007 | planes 1.704 | 0.050 | 49.44 (27.9) | 20.97 (11.8) | 0.993 | cpu_other 0.007 |
| count.masked | 0.091 | writer | 0.061 / 0.066 | 0 | 0.012 | 1.44 (15.8) | 0.98 (10.8) | 0.796 | untimed 0.011 |
| sum.masked | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.6) | 0.50 (8.9) | 0.940 | outside 0.003 |
| hist.masked | 0.025 | writer | 0.016 / 0.020 | 0 | 0.004 | 0.00 (0.0) | 0.28 (10.9) | 0.796 | outside 0.003 |
| hsum.masked | 0.070 | (trace) | 0.021 / - | - | 0.046 | 0.28 (4.0) | 0.56 (8.0) | 0.952 | outside 0.003 |
| middle.masked | 0.564 | thread | - | - | - | - | - | - | - |
| place.masked | 0.091 | writer | 0.067 / 0.085 | 0 | 0.019 | 2.95 (32.5) | 0.53 (5.8) | 0.943 | outside 0.004 |
| setup.masked | 0.169 | pack | 0.026 / 0.072 | mail 0.002 | 0.040 | 1.44 (8.5) | 0.77 (4.6) | 0.404 | cpu_other 0.090 |
| fill.masked | 0.143 | writer | 0.034 / 0.075 | planes 0.008 | 0.033 | 0.92 (6.4) | 20.97 (146.4) | 0.522 | outside 0.059 |
| count.glass | 0.389 | writer | 0.130 / 0.155 | pack 0.120 | 0.120 | 15.91 (40.9) | 0.98 (2.5) | 0.951 | untimed 0.012 |
| sum.glass | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.4) | 0.50 (8.9) | 0.941 | outside 0.003 |
| hist.glass | 0.026 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.45 (17.2) | 0.803 | outside 0.003 |
| hsum.glass | 0.070 | (trace) | 0.033 / - | - | 0.034 | 0.45 (6.4) | 0.91 (13.0) | 0.951 | outside 0.003 |
| middle.glass | 0.678 | thread | - | - | - | - | - | - | - |
| place.glass | 0.094 | writer | 0.070 / 0.088 | 0 | 0.019 | 2.95 (31.4) | 0.55 (5.9) | 0.945 | outside 0.004 |
| setup.glass | 0.509 | pack | 0.349 / 0.397 | mail 0.017, out 0.003 | 0.033 | 15.91 (31.2) | 16.95 (33.3) | 0.790 | cpu_other 0.093 |
| fill.glass | 0.438 | writer | 0.020 / 0.047 | planes 0.350 | 0.056 | 17.14 (39.1) | 20.97 (47.9) | 0.972 | cpu_other 0.007 |
| shade.opaque | 3.650 | pack | 2.570 / 3.552 | in 0.023, pages 0.015 | 0.985 | 152.35 (41.7) | 45.69 (12.5) | 0.985 | cpu_other 0.051 |
| shade.masked | 0.299 | pack | 0.062 / 0.237 | in 0.017, pages 0.001 | 0.161 | 13.71 (45.8) | 1.54 (5.1) | 0.806 | cpu_other 0.053 |
| shade.glass | 0.709 | pack | 0.261 / 0.615 | in 0.022 | 0.372 | 24.55 (34.6) | 4.24 (6.0) | 0.923 | cpu_other 0.049 |
| light | 4.865 | pack | 3.928 / 4.722 | in 0.016, pages 0.030, field_pages 0.030 | 0.810 | 164.08 (33.7) | 12.58 (2.6) | 0.990 | cpu_other 0.045 |
| light_glass | 1.262 | pack | 0.414 / 1.116 | in 0.048, pages 0.007, field_pages 0.002 | 0.739 | 122.55 (97.1) | 12.58 (10.0) | 0.960 | cpu_other 0.046 |
| show | 0.864 | writer | 0.699 / 0.828 | planes 0.002 | 0.129 | 12.58 (14.6) | 4.19 (4.9) | 0.960 | cpu_other 0.030 |
| push | 0.286 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.7) | 0.002 | push 0.282 |

### `gi`, bistro_interior, 1,920 x 1,080

Frame 33.892 ms (committed 33.894 ms, -0.01 %), thread 0.005 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 1.495 | writer | 0.446 / 1.157 | pack 0.318 | 0.712 | 56.18 (37.6) | 1.97 (1.3) | 0.987 | untimed 0.011 |
| sum.opaque | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.3) | 1.00 (8.8) | 0.971 | outside 0.003 |
| middle.opaque | 0.870 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.164 | writer | 0.125 / 0.158 | 0 | 0.034 | 5.41 (33.0) | 0.76 (4.6) | 0.968 | outside 0.004 |
| setup.opaque | 2.209 | pack | 1.469 / 1.953 | mail 0.058, out 0.037 | 0.528 | 56.18 (25.4) | 70.25 (31.8) | 0.942 | cpu_other 0.116 |
| fill.opaque | 3.274 | writer | 0.011 / 0.012 | planes 3.105 | 0.144 | 70.62 (21.6) | 41.78 (12.8) | 0.996 | cpu_other 0.008 |
| count.masked | 0.149 | writer | 0.119 / 0.125 | 0 | 0.011 | 1.44 (9.7) | 1.97 (13.2) | 0.877 | untimed 0.011 |
| sum.masked | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.3) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.masked | 0.025 | writer | 0.016 / 0.020 | 0 | 0.004 | 0.00 (0.0) | 0.43 (17.0) | 0.785 | outside 0.003 |
| hsum.masked | 0.070 | (trace) | 0.032 / - | - | 0.035 | 0.43 (6.1) | 0.87 (12.3) | 0.951 | outside 0.003 |
| middle.masked | 1.030 | thread | - | - | - | - | - | - | - |
| place.masked | 0.164 | writer | 0.125 / 0.158 | 0 | 0.034 | 5.41 (33.0) | 0.53 (3.2) | 0.969 | outside 0.004 |
| setup.masked | 0.234 | pack | 0.031 / 0.083 | mail 0.002 | 0.047 | 1.44 (6.2) | 1.32 (5.7) | 0.348 | cpu_other 0.141 |
| fill.masked | 0.164 | writer | 0.079 / 0.146 | planes 0.006 | 0.060 | 1.49 (9.1) | 41.78 (255.5) | 0.888 | outside 0.009 |
| count.glass | 0.463 | writer | 0.218 / 0.248 | pack 0.021 | 0.204 | 15.91 (34.4) | 1.97 (4.2) | 0.959 | untimed 0.012 |
| sum.glass | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.3) | 1.00 (8.8) | 0.971 | outside 0.003 |
| hist.glass | 0.027 | writer | 0.017 / 0.021 | 0 | 0.004 | 0.00 (0.0) | 0.72 (26.6) | 0.798 | outside 0.003 |
| hsum.glass | 0.073 | (trace) | 0.053 / - | - | 0.016 | 0.72 (9.9) | 1.46 (19.9) | 0.953 | outside 0.003 |
| middle.glass | 1.160 | thread | - | - | - | - | - | - | - |
| place.glass | 0.167 | writer | 0.128 / 0.161 | 0 | 0.034 | 5.41 (32.4) | 0.57 (3.4) | 0.969 | outside 0.004 |
| setup.glass | 0.659 | pack | 0.437 / 0.484 | mail 0.017, out 0.004 | 0.042 | 15.91 (24.1) | 24.30 (36.9) | 0.759 | cpu_other 0.145 |
| fill.glass | 0.658 | writer | 0.020 / 0.059 | planes 0.576 | 0.048 | 24.49 (37.2) | 41.78 (63.5) | 0.981 | cpu_other 0.007 |
| shade.opaque | 6.196 | pack | 4.806 / 6.078 | in 0.024, pages 0.026 | 1.282 | 250.19 (40.4) | 89.26 (14.4) | 0.991 | cpu_other 0.052 |
| shade.masked | 0.522 | pack | 0.139 / 0.431 | in 0.021, pages 0.001 | 0.302 | 19.65 (37.6) | 3.50 (6.7) | 0.888 | cpu_other 0.053 |
| shade.glass | 0.912 | pack | 0.561 / 0.879 | in 0.023 | 0.273 | 34.80 (38.1) | 10.95 (12.0) | 0.940 | cpu_other 0.049 |
| light | 8.649 | pack | 7.702 / 8.414 | in 0.027, pages 0.058, field_pages 0.056 | 0.727 | 283.59 (32.8) | 25.07 (2.9) | 0.991 | cpu_other 0.072 |
| light_glass | 2.106 | pack | 0.868 / 1.960 | in 0.062, pages 0.013, field_pages 0.003 | 1.103 | 218.31 (103.7) | 25.07 (11.9) | 0.973 | cpu_other 0.051 |
| show | 1.541 | writer | 1.395 / 1.503 | planes 0.003 | 0.107 | 25.07 (16.3) | 8.36 (5.4) | 0.977 | cpu_other 0.030 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

### `gi`, modern_hall, 1,024 x 1,024

Frame 13.733 ms (committed 13.734 ms, -0.00 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.154 | writer | 0.065 / 0.132 | 0 | 0.072 | 2.07 (13.4) | 0.98 (6.4) | 0.889 | untimed 0.011 |
| sum.opaque | 0.055 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.8) | 0.50 (9.0) | 0.940 | outside 0.003 |
| hist.opaque | 0.025 | writer | 0.016 / 0.020 | 0 | 0.004 | 0.00 (0.0) | 0.22 (8.6) | 0.786 | outside 0.003 |
| hsum.opaque | 0.070 | (trace) | 0.017 / - | - | 0.050 | 0.22 (3.1) | 0.43 (6.2) | 0.952 | outside 0.003 |
| middle.opaque | 0.508 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.090 | writer | 0.066 / 0.085 | 0 | 0.019 | 2.95 (32.6) | 0.64 (7.1) | 0.943 | outside 0.004 |
| setup.opaque | 0.248 | pack | 0.028 / 0.063 | mail 0.003 | 0.116 | 2.07 (8.4) | 2.41 (9.7) | 0.624 | cpu_other 0.079 |
| fill.opaque | 0.230 | writer | 0.007 / 0.011 | planes 0.200 | 0.011 | 2.68 (11.6) | 20.97 (91.3) | 0.948 | cpu_other 0.006 |
| count.glass | 0.112 | writer | 0.057 / 0.094 | 0 | 0.036 | 0.01 (0.1) | 0.98 (8.8) | 0.838 | untimed 0.011 |
| sum.glass | 0.056 | (trace) | 0.026 / - | - | 0.026 | 0.98 (17.5) | 0.50 (8.9) | 0.941 | outside 0.003 |
| middle.glass | 0.400 | thread | - | - | - | - | - | - | - |
| place.glass | 0.088 | writer | 0.065 / 0.083 | 0 | 0.019 | 2.95 (33.3) | 0.53 (5.9) | 0.941 | outside 0.004 |
| setup.glass | 0.163 | pack | 0.000 / 0.009 | mail 0.001 | 0.076 | 0.01 (0.1) | 0.12 (0.7) | 0.474 | cpu_other 0.079 |
| fill.glass | 0.124 | writer | 0.035 / 0.072 | planes 0.012 | 0.027 | 0.25 (2.0) | 20.97 (168.9) | 0.588 | outside 0.042 |
| shade.opaque | 1.803 | pack | 1.548 / 1.700 | in 0.022, pages 0.005 | 0.172 | 43.19 (24.0) | 46.14 (25.6) | 0.969 | cpu_other 0.050 |
| shade.glass | 0.407 | pack | 0.210 / 0.342 | in 0.009 | 0.135 | 3.32 (8.2) | 6.76 (16.6) | 0.873 | cpu_other 0.046 |
| light | 5.935 | pack | 5.061 / 5.806 | in 0.014, pages 0.029, field_pages 0.031 | 0.749 | 166.13 (28.0) | 12.58 (2.1) | 0.992 | cpu_other 0.045 |
| light_glass | 2.147 | pack | 0.646 / 2.008 | in 0.034, pages 0.004, field_pages 0.002 | 1.410 | 80.95 (37.7) | 12.58 (5.9) | 0.976 | cpu_other 0.046 |
| show | 0.830 | writer | 0.726 / 0.792 | planes 0.001 | 0.068 | 12.58 (15.2) | 4.19 (5.1) | 0.958 | cpu_other 0.029 |
| push | 0.286 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 4.19 (14.7) | 0.002 | push 0.282 |

### `gi`, modern_hall, 1,920 x 1,080

Frame 24.564 ms (committed 24.567 ms, -0.01 %), thread 0.004 ms, codes [0], frames traced 16 of 16, AICLK [1350, 1350] MHz.

| command | ms | CPU | busy mean / most | waiting by kind (mean) | standing still | read MB (GB/s) | written MB (GB/s) | closure | not accounted, largest |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: | --- |
| count.opaque | 0.198 | writer | 0.126 / 0.174 | 0 | 0.054 | 2.07 (10.5) | 1.97 (9.9) | 0.913 | untimed 0.011 |
| sum.opaque | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.8) | 0.971 | outside 0.003 |
| middle.opaque | 0.875 | thread | - | - | - | - | - | - | - |
| place.opaque | 0.164 | writer | 0.125 / 0.156 | 0 | 0.034 | 5.41 (33.1) | 0.77 (4.7) | 0.968 | outside 0.004 |
| setup.opaque | 0.263 | pack | 0.030 / 0.052 | mail 0.003 | 0.073 | 2.07 (7.9) | 4.01 (15.3) | 0.465 | cpu_other 0.124 |
| fill.opaque | 0.454 | writer | 0.014 / 0.019 | planes 0.383 | 0.045 | 4.41 (9.7) | 41.78 (92.0) | 0.974 | cpu_other 0.006 |
| count.glass | 0.182 | writer | 0.114 / 0.158 | 0 | 0.050 | 0.01 (0.1) | 1.97 (10.8) | 0.901 | untimed 0.011 |
| sum.glass | 0.114 | (trace) | 0.061 / - | - | 0.049 | 1.97 (17.2) | 1.00 (8.7) | 0.971 | outside 0.003 |
| middle.glass | 0.818 | thread | - | - | - | - | - | - | - |
| place.glass | 0.161 | writer | 0.122 / 0.154 | 0 | 0.034 | 5.41 (33.7) | 0.54 (3.3) | 0.968 | outside 0.004 |
| setup.glass | 0.218 | pack | 0.000 / 0.008 | mail 0.001 | 0.080 | 0.01 (0.1) | 0.14 (0.6) | 0.371 | cpu_other 0.131 |
| fill.glass | 0.154 | writer | 0.081 / 0.141 | planes 0.005 | 0.055 | 0.25 (1.6) | 41.78 (271.0) | 0.922 | cpu_other 0.006 |
| shade.opaque | 3.383 | pack | 3.042 / 3.275 | in 0.021, pages 0.009 | 0.251 | 73.26 (21.7) | 91.91 (27.2) | 0.982 | cpu_other 0.054 |
| shade.glass | 0.420 | pack | 0.308 / 0.341 | in 0.010 | 0.050 | 4.75 (11.3) | 9.91 (23.6) | 0.876 | cpu_other 0.046 |
| light | 10.821 | pack | 9.833 / 10.586 | in 0.027, pages 0.056, field_pages 0.059 | 0.767 | 279.97 (25.9) | 25.07 (2.3) | 0.993 | cpu_other 0.074 |
| light_glass | 4.093 | pack | 1.376 / 3.897 | in 0.051, pages 0.008, field_pages 0.004 | 2.596 | 160.46 (39.2) | 25.07 (6.1) | 0.986 | cpu_other 0.053 |
| show | 1.567 | writer | 1.422 / 1.527 | planes 0.003 | 0.106 | 25.07 (16.0) | 8.36 (5.3) | 0.978 | cpu_other 0.030 |
| push | 0.564 | (trace) | 0.001 / - | - | 0.000 | 0.00 (0.0) | 8.36 (14.8) | 0.001 | push 0.559 |

## L1

The load's printed table a case, in bytes.

| case | circular buffers | control block and overlay area | slots: service (reader), 1 x 10,240 B (at most) | host transfer buffer | page bounds list | total | left for them |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lit sponza 1024x1024 | 1,057,568 | 17,024 | 10,240 | 93,264 | 944 | 1,179,040 | 1,271,616 |
| lit sponza 1920x1080 | 1,090,336 | 17,024 | 10,240 | 32,848 | 1,136 | 1,151,584 | 1,271,616 |
| lit bistro_interior 1024x1024 | 1,057,568 | 17,024 | 10,240 | 93,264 | 1,472 | 1,179,568 | 1,271,616 |
| lit bistro_interior 1920x1080 | 1,090,336 | 17,024 | 10,240 | 32,848 | 1,808 | 1,152,256 | 1,271,616 |
| lit bistro_exterior 1024x1024 | 1,057,568 | 17,024 | 10,240 | 93,264 | 1,472 | 1,179,568 | 1,271,616 |
| lit bistro_exterior 1920x1080 | 1,090,336 | 17,024 | 10,240 | 32,848 | 1,808 | 1,152,256 | 1,271,616 |
| gi sponza 1024x1024 | 1,087,904 | 17,024 | 10,240 | 32,848 | 1,008 | 1,149,024 | 1,271,616 |
| gi sponza 1920x1080 | 1,120,672 | 17,024 | 10,240 | 32,848 | 1,200 | 1,181,984 | 1,271,616 |
| gi bistro_interior 1024x1024 | 1,087,904 | 17,024 | 10,240 | 32,848 | 1,536 | 1,149,552 | 1,271,616 |
| gi bistro_interior 1920x1080 | 1,120,672 | 17,024 | 10,240 | 32,848 | 1,872 | 1,182,656 | 1,271,616 |
| gi modern_hall 1024x1024 | 1,087,904 | 17,024 | 10,240 | 32,848 | 1,312 | 1,149,328 | 1,271,616 |
| gi modern_hall 1920x1080 | 1,120,672 | 17,024 | 10,240 | 32,848 | 1,600 | 1,182,384 | 1,271,616 |

## Code sizes

Each kernel's ELF, in bytes.

| case | reader text / data / bss | writer text / data / bss | unpack text / data / bss | math text / data / bss | pack text / data / bss |
| --- | --- | --- | --- | --- | --- |
| lit sponza 1024x1024 | 50,052 / 428 / 68 | 49,056 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,396 / 304 / 32 |
| lit sponza 1920x1080 | 50,136 / 428 / 68 | 49,436 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,356 / 304 / 32 |
| lit bistro_interior 1024x1024 | 50,052 / 428 / 68 | 49,056 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,396 / 304 / 32 |
| lit bistro_interior 1920x1080 | 50,136 / 428 / 68 | 49,436 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,356 / 304 / 32 |
| lit bistro_exterior 1024x1024 | 50,052 / 428 / 68 | 49,056 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,396 / 304 / 32 |
| lit bistro_exterior 1920x1080 | 50,136 / 428 / 68 | 49,436 / 380 / 100 | 13,164 / 332 / 8 | 3,268 / 68 / 8 | 111,356 / 304 / 32 |
| gi sponza 1024x1024 | 49,084 / 536 / 68 | 53,136 / 488 / 100 | 23,500 / 592 / 36 | 12,088 / 200 / 32 | 117,644 / 312 / 56 |
| gi sponza 1920x1080 | 49,284 / 536 / 68 | 53,364 / 488 / 100 | 23,500 / 592 / 36 | 12,088 / 200 / 32 | 117,600 / 312 / 56 |
| gi bistro_interior 1024x1024 | 49,080 / 536 / 68 | 53,132 / 488 / 100 | 23,476 / 592 / 40 | 12,100 / 200 / 36 | 117,656 / 312 / 60 |
| gi bistro_interior 1920x1080 | 49,280 / 536 / 68 | 53,360 / 488 / 100 | 23,476 / 592 / 40 | 12,100 / 200 / 36 | 117,612 / 312 / 60 |
| gi modern_hall 1024x1024 | 49,088 / 536 / 68 | 53,152 / 488 / 100 | 23,468 / 592 / 40 | 12,100 / 200 / 36 | 117,652 / 312 / 60 |
| gi modern_hall 1920x1080 | 49,292 / 536 / 68 | 53,380 / 488 / 100 | 23,468 / 592 / 40 | 12,100 / 200 / 36 | 117,608 / 312 / 60 |

### The handlers' bytes in the command switch, `gi`, modern_hall, 1,920 x 1,080

| handler | reader | writer | unpack | math | pack |
| --- | ---: | ---: | ---: | ---: | ---: |
| apply | 300 | 364 | 8 | 0 | 8 |
| copy | 2436 | 1012 | 636 | 0 | 904 |
| count | 644 | 884 | 712 | 0 | 1108 |
| dispatch | 68 | 208 | 168 | 0 | 152 |
| fill | 2264 | 3232 | 632 | 0 | 2196 |
| hist | 40 | 648 | 20 | 0 | 32 |
| hsum | 708 | 756 | 1280 | 0 | 4152 |
| light | 220 | 76 | 204 | 0 | 240 |
| load_empty | 304 | 2088 | 440 | 0 | 112 |
| place | 392 | 880 | 208 | 0 | 12 |
| setup | 960 | 596 | 748 | 0 | 836 |
| setup_shaded | 3256 | 1172 | 796 | 0 | 1124 |
| shade | 384 | 236 | 452 | 0 | 24 |
| show | 1148 | 2632 | 0 | 0 | 0 |
| sum | 772 | 828 | 2856 | 0 | 3544 |

## Per-item constants

`fit.json`: for SHADE (the pack thread, each layer's command a point), LIGHT (the pack
thread, its first form) and SHOW (the writer), a least-squares fit without a constant
term of a core's busy cycles against its items (SHADE, LIGHT: tiles; SHOW: items), its
rows and its fetched pages (SHADE: texture pages; LIGHT: light and field pages; SHOW:
none), in cycles each; `residual`: the RMS over the cores with work of (fitted - busy)
/ busy; `cores`: the points fitted, each pipeline's scenes alone and together.

| pipeline.stage | scene | items | rows | pages | residual | cores |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| gi.SHADE | all | 185,757.0 | 583.8 | 963.9 | 1.5244 | 1680 |
| gi.SHADE | bistro_interior | 153,050.8 | 255.6 | 9,231.5 | 1.8725 | 720 |
| gi.SHADE | modern_hall | 227,270.3 | 77.5 | 1,877.9 | 0.0230 | 480 |
| gi.SHADE | sponza | 173,945.5 | 609.3 | 782.7 | 0.8417 | 480 |
| gi.LIGHT | all | -305,403.5 | 21,237.5 | 12,518.0 | 0.1565 | 720 |
| gi.LIGHT | bistro_interior | -2,729.9 | 17,266.8 | 2,816.8 | 0.0084 | 240 |
| gi.LIGHT | modern_hall | -19,057.4 | 22,559.7 | 3,622.4 | 0.0075 | 240 |
| gi.LIGHT | sponza | 434.2 | 13,893.0 | 4,080.0 | 0.0079 | 240 |
| gi.SHOW | all | -2,590.2 | 3,575.6 | 0.0 | 0.0224 | 720 |
| gi.SHOW | bistro_interior | -658.6 | 3,481.2 | 0.0 | 0.0239 | 240 |
| gi.SHOW | modern_hall | 28,245.7 | 2,652.9 | 0.0 | 0.0210 | 240 |
| gi.SHOW | sponza | 108.7 | 3,477.6 | 0.0 | 0.0052 | 240 |
| lit.SHADE | all | 189,708.1 | 540.7 | 1,456.0 | 1.4704 | 1920 |
| lit.SHADE | bistro_exterior | 195,563.8 | 390.4 | 4,357.7 | 0.1657 | 720 |
| lit.SHADE | bistro_interior | 153,008.0 | 255.4 | 9,237.5 | 1.8737 | 720 |
| lit.SHADE | sponza | 173,677.2 | 610.0 | 785.4 | 0.8402 | 480 |
| lit.LIGHT | all | 301,598.4 | -4,732.5 | 8,894.9 | 0.1469 | 720 |
| lit.LIGHT | bistro_exterior | 171.1 | 5,475.8 | 3,046.8 | 0.0102 | 240 |
| lit.LIGHT | bistro_interior | 4,263.5 | 8,569.6 | 1,994.9 | 0.0089 | 240 |
| lit.LIGHT | sponza | 177.1 | 5,667.6 | 3,408.5 | 0.0129 | 240 |
| lit.SHOW | all | -9,748.7 | 3,804.2 | 0.0 | 0.0164 | 720 |
| lit.SHOW | bistro_exterior | 110.0 | 3,518.6 | 0.0 | 0.0057 | 240 |
| lit.SHOW | bistro_interior | -815.3 | 3,482.5 | 0.0 | 0.0240 | 240 |
| lit.SHOW | sponza | 109.7 | 3,509.1 | 0.0 | 0.0042 | 240 |
