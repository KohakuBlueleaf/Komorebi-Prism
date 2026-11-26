# The account of the threads' frame

Where the time and the bytes of a frame go when the frame is run as threads: the
dispatcher's pulls (count, place, tile) handed out by the frame's X280 thread, each
core taking threads one by one. Four ways of handing out are compared on the same
frames: the stage-wise preset, and the threads' preset with the tile pull's choice
`kept` (each core keeps the slices it was given), `order` (the next slice not yet
empty) and `prefer` (a slice near the core's last). Nothing was tuned for these
numbers: every constant is the preset's.

- Card: one Blackhole P150A, 120 cores, AICLK 1,350 MHz before and after every run as
  the runs report it. The card was held by the runs alone (a lock a card); the other
  card of the machine ran other jobs throughout.
- Date: 2026-11-27 (UTC+8), Komorebi 0.5.3. Tree: the threads' branch with the account
  below; every record from one build of each preset.
- Each case: `scripts/run/threads_account.py --pipeline P --scene S --view V --size
  1920 1080 --frames 16 --way W --want PICTURE --card C [--account 512]`: one load, 16
  frames at the view's camera. The stage-wise run writes its first picture; every
  threads frame's picture is compared with it and every stage-wise frame with its
  first. Three runs a way, interleaved (a way's runs never one after another).
- A number is the median over frames 2 to 16 of a run, then the median of the three
  runs; the range is the three runs' medians. A core's number: core by core, then the
  median, the least and the most over the 120 cores.
- Every frame of every run below: code 0, picture equal (0 pixels different).
- The raw records stay on disk, outside the repository.

## The account in the frame (build option `account`)

The threads' host option `account` (the records a core keeps; 0, the default, builds
nothing of it) compiles the account into the handler `work` and the dispatcher
(`frame/kernels/account.hpp`, `PRISM_FRAME_ACCOUNT`, `DP_ACCOUNT`):

- Counters a command, by (view, pull), in the handler's memory: on each mover the
  threads taken, the cycles waiting for an answer (`ask`), for "none left" (`none`),
  for its own thread before asking the next (`ahead`), the drain at the end, the
  command's span, the cycles running its share of threads (`run`) and serving the
  compute side (`serve`); the bytes it moved by path. On each compute CPU the cycles in
  threads, in each step, and the threads. Mover A writes the block to the core's page
  at the command's end, once the others have written theirs.
- A record a thread, written by mover A to the core's page when the thread ends: the
  view and pull, its number, when it was asked for, when the answer came, when it
  started, when each mover ended it, the cost told to the X280, and pack's end of each
  step of a tile thread. A ring of `account` records a core.
- On the X280, each core's choice: answers with a thread, answers "none left", the
  timer's ticks in the choosing function (the tile pull's choice only).

Read after each frame (the host reads the pages between frames; the X280's words after
the stop): `prism.check.threads.account_read`.

Its cost: `order` on Sponza's overview, `textured`, 13.832 ms without the account and
13.970 ms with it (+0.138 ms, 1.0 %; three runs each, ranges 13.731 to 13.960 and 13.877
to 13.995); most of it in the place pull (+0.086 ms: a count added at each 128-byte
list write). On the artists' scenes the difference is inside the runs' spread
(hidden alley 75.836 against 76.151 ms, lynxsdesign 50.506 against 50.510 ms). The
records go to DRAM (64 bytes a thread, one write); the counters stay in L1 (1,024 bytes
of the handler's memory) until the command's end.

### The clocks on one axis

Every core time is the core's wall clock (`km::wall`, the AICLK's cycles), the clock
Komorebi's trace uses: a record's times and the trace's rows are on the same axis. The
cores' clocks agree: the 120 cores' first asks of a frame lie within 5,402 cycles
(4.0 us) of each other, which is the dispatch's own spread. The X280's times (its timer
at 50 MHz, the dispatcher's phase marks) are durations; a phase is placed on the cores'
axis by its threads: it begins at its first ask less the difference below, and ends at
its last thread's end. The difference between the X280's phase and its threads' extent
(first ask to last end) is the dispatch's cost at the phase's two ends: Sponza `order`
0.126 ms (count), 0.026 ms (place), 0.082 ms (tile).

## Four ways of handing out

Times in ms. Stage-wise phases are its commands grouped: count the raster count passes;
sums the sum and histogram passes; running the middle pass; place the place passes;
set-up the set-up passes; tile fill, shade, light, show and push. The threads' place
pull runs the set-up pass and the list writes together: it stands against the
stage-wise place and set-up together, and the threads' tile pull against the
stage-wise tile column. The threads' `sums` is the sums alone
(the dispatcher's mark spans the running sum too; it is taken off here).

Heavy tiles, what each form did in every table of this section: stage-wise: tiles past
0.33 of the mean cost a core cut into bands (each frame, by its middle pass,
`stages/raster/thread/raster_middle.c`, up to 16 bands); threads: no tile cut (heavy 0,
the threads' host's default). The two rules differ in kind (a cost against the frame's
mean, against a fixed weight); a cut at a weight taken from the frame's data is
measured apart below ("Heavy tiles cut at a weight from the data").

### Sponza, overview

| preset | way | frame (runs' range) | count | sums | running | place | set-up | tile |
|---|---|---|---:|---:|---:|---:|---:|---:|
| textured | stage-wise | 16.428 (16.425 to 16.432) | 0.940 | 0.329 | 2.056 | 0.339 | 1.525 | 11.234 |
| textured | kept | 23.405 (23.388 to 23.419) | 1.040 | 0.271 | 0.048 | 1.799 | (in place) | 20.243 |
| textured | order | 13.901 (13.858 to 13.923) | 1.041 | 0.271 | 0.049 | 1.806 | (in place) | 10.647 |
| textured | prefer | 13.134 (13.072 to 13.188) | 1.041 | 0.271 | 0.049 | 1.802 | (in place) | 9.930 |
| lit | stage-wise | 18.838 (18.838 to 18.964) | 0.944 | 0.329 | 2.028 | 0.339 | 1.528 | 13.668 |
| lit | order | 15.326 (15.167 to 15.338) | 0.987 | 0.272 | 0.050 | 1.816 | (in place) | 12.142 |
| lit | kept (account) | 25.694 (25.667 to 25.748) | 1.042 | 0.271 | 0.050 | 1.909 | (in place) | 22.398 |
| lit | order (account) | 15.344 (15.231 to 15.664) | 1.041 | 0.272 | 0.050 | 1.914 | (in place) | 12.093 |
| lit | prefer (account) | 14.584 (14.552 to 14.662) | 1.041 | 0.272 | 0.050 | 1.919 | (in place) | 11.301 |

### Hidden alley (camera)

| preset | way | frame (runs' range) | count | sums | running | place | set-up | tile |
|---|---|---|---:|---:|---:|---:|---:|---:|
| textured | stage-wise | 53.544 (53.541 to 53.554) | 9.462 | 0.331 | 2.068 | 0.340 | 12.998 | 28.335 |
| textured | order | 75.836 (75.637 to 77.047) | 9.668 | 0.270 | 0.051 | 14.244 | (in place) | 51.477 |
| textured | kept (account) | 188.315 (188.307 to 188.329) | 9.684 | 0.272 | 0.050 | 14.400 | (in place) | 163.930 |
| textured | order (account) | 76.151 (75.787 to 76.516) | 9.679 | 0.272 | 0.050 | 14.370 | (in place) | 51.821 |
| textured | prefer (account) | 61.899 (61.873 to 61.989) | 9.678 | 0.271 | 0.051 | 14.384 | (in place) | 37.505 |
| lit | stage-wise | 57.700 (57.681 to 57.707) | 9.531 | 0.333 | 2.036 | 0.339 | 13.024 | 32.423 |
| lit | order | 59.962 (59.559 to 60.329) | 9.670 | 0.272 | 0.051 | 14.275 | (in place) | 35.707 |
| lit | kept (account) | 146.139 (146.124 to 146.161) | 9.677 | 0.271 | 0.051 | 14.354 | (in place) | 121.810 |
| lit | order (account) | 59.573 (59.542 to 59.938) | 9.676 | 0.271 | 0.051 | 14.363 | (in place) | 35.232 |
| lit | prefer (account) | 49.396 (49.279 to 49.404) | 9.673 | 0.272 | 0.051 | 14.340 | (in place) | 25.029 |

### Lynxsdesign (camera)

| preset | way | frame (runs' range) | count | sums | running | place | set-up | tile |
|---|---|---|---:|---:|---:|---:|---:|---:|
| textured | stage-wise | 42.843 (42.842 to 42.844) | 8.254 | 0.333 | 1.990 | 0.337 | 11.641 | 20.280 |
| textured | order | 50.506 (49.899 to 50.590) | 9.410 | 0.271 | 0.051 | 13.014 | (in place) | 27.774 |
| textured | kept (account) | 109.193 (109.160 to 109.207) | 9.429 | 0.271 | 0.050 | 13.131 | (in place) | 86.304 |
| textured | order (account) | 50.510 (49.715 to 51.267) | 9.428 | 0.270 | 0.051 | 13.115 | (in place) | 27.635 |
| textured | prefer (account) | 45.050 (44.890 to 45.269) | 9.428 | 0.270 | 0.051 | 13.127 | (in place) | 22.279 |
| lit | stage-wise | 48.640 (48.639 to 48.643) | 8.371 | 0.333 | 1.969 | 0.337 | 11.676 | 25.952 |
| lit | order | 46.941 (46.812 to 46.949) | 9.409 | 0.271 | 0.051 | 13.017 | (in place) | 24.191 |
| lit | kept (account) | 87.562 (87.541 to 87.568) | 9.429 | 0.271 | 0.050 | 13.079 | (in place) | 64.731 |
| lit | order (account) | 46.957 (46.926 to 47.518) | 9.429 | 0.271 | 0.051 | 13.079 | (in place) | 24.124 |
| lit | prefer (account) | 44.571 (44.564 to 44.587) | 9.429 | 0.271 | 0.051 | 13.078 | (in place) | 21.727 |

### Classroom (camera; three layers: opaque, masked, glass)

| preset | way | frame (runs' range) | count | sums | running | place | set-up | tile |
|---|---|---|---:|---:|---:|---:|---:|---:|
| textured | stage-wise | 23.216 (23.208 to 23.217) | 2.301 | 0.622 | 3.032 | 0.506 | 2.850 | 13.933 |
| textured | order | 26.812 (26.596 to 26.880) | 1.730 | 0.397 | 0.060 | 2.694 | (in place) | 21.881 |
| textured | kept (account) | 33.890 (33.874 to 33.907) | 1.734 | 0.396 | 0.060 | 2.730 | (in place) | 28.974 |
| textured | order (account) | 26.554 (26.521 to 26.643) | 1.733 | 0.396 | 0.060 | 2.729 | (in place) | 21.628 |
| textured | prefer (account) | 23.469 (23.411 to 23.500) | 1.735 | 0.397 | 0.060 | 2.727 | (in place) | 18.573 |

`lit` on the two artists' scenes draws one view a frame here: the frame loop of these
runs sends no SUN command, so both forms use the sun's map made at the load and no
sun's DEPTH view is in these frames (below, "What is not measured").

## Heavy tiles cut at a weight from the data

A measurement of what cutting gives, not a preset change: the presets keep heavy 0.
The threads' form with its existing option `heavy` set to 0.33 x (the frame's entries
over all layers / 120 cores), the stage-wise rule's weight-only form, computed on the
host from the model's tile counts at the view's camera (`prism.stages.raster.model.
counts.kept_counts`, the counts the threads' host sizes its lists with). A tile whose
entries pass it is cut into ceil(entries / heavy) bands. Three runs a way, 16 frames,
no account; every frame code 0 and every picture equal to the stage-wise one. The
stage-wise and heavy-0 rows are those of the tables above. ms; place for stage-wise is
its place + set-up; sums without the running sum (it holds the cut's work with a heavy).

| scene | preset | heavy | tiles cut / bands | way | frame | count | sums | place | tile |
|---|---|---:|---|---|---|---:|---:|---:|---:|
| Sponza | textured | 807 | 34 / 70 | stage-wise | 16.428 | 0.940 | 0.329 | 0.339 + 1.525 | 11.234 |
| Sponza | textured | 807 | 34 / 70 | order, heavy 0 | 13.901 | 1.041 | 0.271 | 1.806 | 10.647 |
| Sponza | textured | 807 | 34 / 70 | prefer, heavy 0 | 13.134 | 1.041 | 0.271 | 1.802 | 9.930 |
| Sponza | textured | 807 | 34 / 70 | order, heavy 807 | 14.936 (14.717 to 14.968) | 0.985 | 1.214 | 1.838 | 10.819 |
| Sponza | textured | 807 | 34 / 70 | prefer, heavy 807 | 14.016 (14.007 to 14.226) | 0.985 | 1.214 | 1.841 | 9.962 |
| Sponza | lit | 807 | 34 / 70 | stage-wise | 18.838 | 0.944 | 0.329 | 0.339 + 1.528 | 13.668 |
| Sponza | lit | 807 | 34 / 70 | order, heavy 0 | 15.326 | 0.987 | 0.272 | 1.816 | 12.142 |
| Sponza | lit | 807 | 34 / 70 | prefer, heavy 0 (account) | 14.584 | 1.041 | 0.272 | 1.919 | 11.301 |
| Sponza | lit | 807 | 34 / 70 | order, heavy 807 | 16.268 (16.228 to 16.293) | 0.984 | 1.215 | 1.848 | 12.105 |
| Sponza | lit | 807 | 34 / 70 | prefer, heavy 807 | 15.469 (15.462 to 15.479) | 0.995 | 1.214 | 1.858 | 11.311 |
| hidden alley | textured | 7,053 | 94 / 213 | stage-wise | 53.544 | 9.462 | 0.331 | 0.340 + 12.998 | 28.335 |
| hidden alley | textured | 7,053 | 94 / 213 | order, heavy 0 | 75.836 | 9.668 | 0.270 | 14.244 | 51.477 |
| hidden alley | textured | 7,053 | 94 / 213 | prefer, heavy 0 (account) | 61.899 | 9.678 | 0.271 | 14.384 | 37.505 |
| hidden alley | textured | 7,053 | 94 / 213 | order, heavy 7,053 | 57.206 (56.952 to 57.237) | 9.667 | 2.888 | 14.348 | 30.282 |
| hidden alley | textured | 7,053 | 94 / 213 | prefer, heavy 7,053 | 53.663 (53.659 to 53.779) | 9.666 | 2.888 | 14.338 | 26.774 |
| hidden alley | lit | 7,053 | 94 / 213 | stage-wise | 57.700 | 9.531 | 0.333 | 0.339 + 13.024 | 32.423 |
| hidden alley | lit | 7,053 | 94 / 213 | order, heavy 0 | 59.962 | 9.670 | 0.272 | 14.275 | 35.707 |
| hidden alley | lit | 7,053 | 94 / 213 | prefer, heavy 0 (account) | 49.396 | 9.673 | 0.272 | 14.340 | 25.029 |
| hidden alley | lit | 7,053 | 94 / 213 | order, heavy 7,053 | 53.823 (53.768 to 53.924) | 9.668 | 2.888 | 14.355 | 26.855 |
| hidden alley | lit | 7,053 | 94 / 213 | prefer, heavy 7,053 | 52.119 (51.979 to 52.170) | 9.670 | 2.888 | 14.316 | 25.161 |
| lynxsdesign | textured | 5,700 | 116 / 248 | stage-wise | 42.843 | 8.254 | 0.333 | 0.337 + 11.641 | 20.280 |
| lynxsdesign | textured | 5,700 | 116 / 248 | order, heavy 0 | 50.506 | 9.410 | 0.271 | 13.014 | 27.774 |
| lynxsdesign | textured | 5,700 | 116 / 248 | prefer, heavy 0 (account) | 45.050 | 9.428 | 0.270 | 13.127 | 22.279 |
| lynxsdesign | textured | 5,700 | 116 / 248 | order, heavy 5,700 | 47.409 (47.283 to 47.468) | 9.410 | 2.398 | 13.074 | 22.542 |
| lynxsdesign | textured | 5,700 | 116 / 248 | prefer, heavy 5,700 | 44.608 (44.560 to 44.622) | 9.410 | 2.398 | 13.058 | 19.689 |
| lynxsdesign | lit | 5,700 | 116 / 248 | stage-wise | 48.640 | 8.371 | 0.333 | 0.337 + 11.676 | 25.952 |
| lynxsdesign | lit | 5,700 | 116 / 248 | order, heavy 0 | 46.941 | 9.409 | 0.271 | 13.017 | 24.191 |
| lynxsdesign | lit | 5,700 | 116 / 248 | prefer, heavy 0 (account) | 44.571 | 9.429 | 0.271 | 13.078 | 21.727 |
| lynxsdesign | lit | 5,700 | 116 / 248 | order, heavy 5,700 | 47.461 (47.371 to 47.519) | 9.410 | 2.399 | 13.093 | 22.530 |
| lynxsdesign | lit | 5,700 | 116 / 248 | prefer, heavy 5,700 | 46.667 (46.666 to 46.676) | 9.410 | 2.399 | 13.056 | 21.739 |
| classroom | textured | 1,837 | 23 / 89 | stage-wise | 23.216 | 2.301 | 0.622 | 0.506 + 2.850 | 13.933 |
| classroom | textured | 1,837 | 23 / 89 | order, heavy 0 | 26.812 | 1.730 | 0.397 | 2.694 | 21.881 |
| classroom | textured | 1,837 | 23 / 89 | prefer, heavy 0 (account) | 23.469 | 1.735 | 0.397 | 2.727 | 18.573 |
| classroom | textured | 1,837 | 23 / 89 | order, heavy 1,837 | 19.300 (19.186 to 19.427) | 1.731 | 2.030 | 2.693 | 12.786 |
| classroom | textured | 1,837 | 23 / 89 | prefer, heavy 1,837 | 18.687 (18.651 to 18.793) | 1.732 | 2.031 | 2.699 | 12.175 |

The heaviest tile holds 2,261 entries on Sponza, 36,438 on hidden alley, 19,996 on
lynxsdesign, 21,144 on classroom (the frame's entries: 293,571; 2,564,913; 2,072,780;
668,006). With the cut the tile pull falls where one tile set its end (hidden alley
`textured` `prefer` 37.5 to 26.8 ms, `order` 51.5 to 30.3; classroom 18.6 to 12.2 and
21.9 to 12.8), and the sums phase grows by the cut's work: 0.94 ms on Sponza, 2.6 ms on
hidden alley, 2.1 on lynxsdesign, 1.6 on classroom. Where no single tile ended the tile
pull the frame is slower with the cut (Sponza `prefer` 13.13 to 14.02 ms; hidden alley
`lit` `prefer` 49.40 to 52.12; lynxsdesign `lit` `prefer` 44.57 to 46.67).

## Bytes a frame by path

From the movers' counters (MB a frame, all cores). They are the same in every way of
handing out and in every run: the paths do not depend on which core takes a thread.

| scene, preset | triangle blocks (count / place) | shade blocks (place) | lists (place writes / tile reads) | records and slices | texture pages asked (tile) | rows out | counts, histograms, positions (count / place) |
|---|---|---:|---|---:|---:|---:|---|
| Sponza, textured | 37.77 (18.88 / 18.88) | 4.20 | 121.05 (37.58 / 83.48) | 2.30 | 108.94 | 8.36 | 45.6 (33.4 / 12.2) |
| Sponza, lit | 37.77 (18.88 / 18.88) | 4.20 | 121.05 (37.58 / 83.48) | 2.29 | 276.41 | 8.36 | 45.6 (33.4 / 12.2) |
| hidden alley, textured | 1,295.15 (647.57 / 647.57) | 143.91 | 995.37 (328.31 / 667.06) | 2.35 | 95.14 | 8.36 | 46.0 (33.4 / 12.5) |

| lynxsdesign, textured | 1,268.13 (634.06 / 634.06) | 140.90 | 805.48 (265.32 / 540.16) | 2.35 | 48.96 | 8.36 | 46.0 (33.4 / 12.5) |
| classroom, textured | 180.31 (90.16 / 90.16) | 20.03 | 264.61 (85.50 / 179.10) | 2.61 | 88.24 | 8.36 | 64.2 (50.1 / 14.1) |
| hidden alley, lit | 1,295.15 (647.57 / 647.57) | 143.91 | 995.37 (328.31 / 667.06) | 2.35 | 1,172.14 | 8.36 | 46.0 (33.4 / 12.5) |
| lynxsdesign, lit | 1,268.13 (634.06 / 634.06) | 140.90 | 805.48 (265.32 / 540.16) | 2.35 | 223.60 | 8.36 | 46.0 (33.4 / 12.5) |

Sponza `textured`'s split by pull is from the `lit` runs (the same count and place
passes over the same geometry; the totals are equal). The triangle blocks are read
twice, once by the count pull and again by the place pull. The place pull writes each
list entry as one 128-byte write. The tile pull reads the lists once (the list passes of
every step together). "Texture pages asked" are the pages the compute side asks the
movers for: the material's texture pages and, in `lit`, the light's pages, not split.
Besides these: the camera (`other`) and the records' and slices' reads.

## A core's time

The tile pull, `textured`, Sponza (ms a frame a core; the median, least and most over
the 120 cores). `span` is the command on that mover from start to end; `run` its share
of the threads; `ask` waiting for an answer (mover B: for mover A's descriptor);
`ahead` mover A waiting for its own thread before asking the next; `serve` serving
the compute side's page requests.

| way | A span | A run | A ask | A none | A ahead | A drain | B run | B ask | serve (A) |
|---|---|---|---|---|---|---|---|---|---|
| kept | 9.29 (2.15 to 20.25) | 8.72 (0.21 to 19.30) | 0.013 | 0.000 | 0.26 (0.00 to 2.54) | 0.19 | 8.41 | 0.89 | 0.83 |
| order | 9.11 (8.19 to 10.71) | 8.15 (6.82 to 9.94) | 0.014 | 0.000 | 0.52 (0.00 to 1.40) | 0.31 | 7.72 | 1.11 | 0.93 |
| prefer | 9.12 (8.66 to 9.95) | 8.36 (5.52 to 9.27) | 0.049 (0.008 to 0.130) | 0.000 | 0.33 (0.00 to 3.00) | 0.26 | 7.98 | 0.87 | 0.83 |

Standing still: a core asked and not yet answered is `ask` (0.013 to 0.049 ms a frame:
the port holds an answer before it is asked, so an ask is a read of it, 0.30 us at the
median); "none left" costs nothing measurable (0.0001 ms). The core's real standing
still is after its last thread: the phase lasts as long as its slowest core, so a core
waits the phase less its own span: in `order` 1.6 ms at the median (10.74 less 9.11),
in `kept` 11.0 ms at the median and 18.1 ms on the least-loaded core.

The count and place pulls (Sponza, every way alike): count A span 0.46 ms (0.39 to
0.87), mover B running 0.43 ms; place 0.80 ms (0.53 to 1.87), mover B running 0.77 ms
(0.49 to 1.84). The longest place thread (1.26 ms at the median over frames, 1.72 ms at
most) sets the place pull's end: the X280's place phase is 1.90 ms, its threads'
extent 1.87 ms (below, "The place pull taken apart").

On the artists' scenes the count and place pulls are long and even over the cores
(hidden alley, `textured`, `order`; 70,267 ranges a pull, 557 to 598 a core):

| pull | A span | A run | A ask | A ahead | B run | B ask |
|---|---|---|---|---|---|---|
| count | 9.36 (9.36 to 9.39) | 3.01 | 4.54 (4.15 to 4.84) | 0.96 | 8.21 | 0.94 |
| place | 13.88 (13.49 to 14.35) | 11.67 | 0.53 | 0.81 | 13.54 | 0.13 |

In the count pull mover A waits for an answer 4.5 ms of its 9.4 (an ask's median is
10.5 us there, against 0.3 us elsewhere: the records below), and mover B,
which moves the triangle blocks, waits 0.9 ms for mover A. In the place pull mover B
runs 13.5 of 13.9 ms, 9.9 ms of it waiting for the compute side's pages. lynxsdesign is alike (count 9.16 ms, A ask 4.60; place 12.67 ms,
B run 12.33).

The tile pull on hidden alley, `prefer`: a core's span 24.53 ms at the median (24.33
to 37.48); one tile thread of 34.5 ms (the records' longest) sets the pull's end
(37.51 ms).

## Standing still by wait

Each core's time between the frame's first command and the tile pull's end, by what
it waits for. The pulls' threads come from the records; the commands (count, sums,
place, tile) from Komorebi's trace of the same runs, on the same clock (the trace's
rows: when a core took a command and when it was done with it). "End of pull" is the
time a core is done while the command waits for its slowest core; "between" is the
time from a command's last core to the next command's taking: the frame's thread
between two pulls. Core-ms a frame (the 120 cores together), then a core's median,
least and most. Three runs, 15 frames each (`textured`; `--account --trace 512`).

| wait | Sponza `order` | Sponza `prefer` | Sponza `kept` | hidden alley `prefer` |
|---|---|---|---|---|
| count: asked, not yet answered | 5.8 (0.046; 0.023 to 0.088) | 5.7 (0.046) | 5.8 (0.046) | 544.0 (4.54; 4.16 to 4.84) |
| count: end of pull | 47.2 (0.396; 0 to 0.471) | 47.4 (0.398) | 47.3 (0.397) | 2.4 (0.018; 0 to 0.050) |
| sums: end of the command | 27.3 (0.260; 0 to 0.262) | 27.3 (0.260) | 27.3 (0.260) | 27.3 (0.261) |
| place: asked, not yet answered | 4.2 (0.035) | 4.2 (0.035) | 4.2 (0.035) | 61.7 (0.514; 0.213 to 0.896) |
| place: end of pull | 127.7 (1.074; 0 to 1.353) | 129.4 (1.086) | 128.0 (1.077) | 57.4 (0.478; 0 to 0.865) |
| tile: asked, not yet answered | 1.9 (0.014) | 6.8 (0.051; 0.008 to 0.130) | 1.7 (0.013) | 6.7 (0.050) |
| tile: end of pull | 184.2 (1.585; 0 to 2.566) | 91.3 (0.778; 0 to 1.301) | 1,337.3 (10.95; 0 to 18.11) | 1,480.9 (12.71; 0 to 12.97) |
| between count and sums | 3.8 (0.032) | 3.8 (0.032) | 3.7 (0.031) | 22.0 (0.183) |
| between sums and place (running sum, words) | 7.1 (0.059) | 7.1 (0.059) | 7.0 (0.059) | 7.1 (0.059) |
| between place and tile | 2.5 (0.021) | 2.5 (0.021) | 2.5 (0.021) | 2.7 (0.022) |
| the X280's frame outside the cores' | 10.8 (0.090) | 8.5 (0.071) | 3.2 (0.026) | 3.3 (0.028) |
| a core before its first ask (three pulls) | 9.9 (0.082) | 9.9 (0.082) | 9.9 (0.082) | 9.9 (0.082) |
| a core's own end of the count command | 10.6 (0.086) | 10.5 (0.085) | 10.5 (0.086) | 12.3 (0.103) |
| the frame on the cores (first take to tile's end) | 1,658.5 (13.82) | 1,572.3 (13.10) | 2,817.6 (23.48) | 7,406.7 (61.72) |

"None left" ends each pull once a core (one exchange a core a pull); its wait is
0.0001 ms. The sums command runs on one core (0.263 ms) while the other 119 take it and
are done at once (0.003 ms): they stand 0.26 ms. "The X280's frame outside the cores'"
is the frame's time on the X280 less the cores' first take to the tile pull's end: the
frame's start and its end after the tile pull.

On Sponza the standing still at the pulls' ends is 386 of the frame's 1,659 core-ms
(23 %, `order`): tile 184, place 128, count 47, sums 27; the frame's thread between
pulls costs 0.11 ms of the frame (13.4 core-ms). On hidden alley the tile pull's end is
almost all of it (1,481 core-ms: one heavy tile thread), and the count pull's asks are
next (544 core-ms).

## What asking costs

Each pull's exchanges a core (the threads it was answered, plus one "none left"), the
time from a core's ask to its answer over all asks (us), and the asks' share of the
threads' lives (ask to end, summed) and of the command on the cores (summed):

| case | pull | threads a core (least / median / most) | ask to answer: median [5th, 95th, most] | of the threads' lives | of the command |
|---|---|---|---|---:|---:|
| Sponza `order` | count | 4 / 18 / 21 | 0.31 [0.23, 12.79, 24.11] | 5.5 % | 8.6 % |
| Sponza `order` | place | 4 / 18 / 21 | 0.30 [0.21, 13.89, 31.08] | 2.3 % | 4.3 % |
| Sponza `order` | tile | 12 / 17 / 23 | 0.29 [0.21, 4.32, 27.21] | 0.1 % | 0.2 % |
| Sponza `prefer` | tile | 10 / 15 / 35 | 0.29 [0.21, 12.48, 134.95] | 0.4 % | 0.6 % |
| Sponza `kept` | tile | 12 / 16 / 32 | 0.29 [0.21, 3.34, 25.23] | 0.1 % | 0.2 % |
| hidden alley `prefer` | count | 557 / 587 / 600 | 10.46 [0.29, 11.09, 24.42] | 27.8 % | 47.9 % |
| hidden alley `prefer` | place | 557 / 587 / 600 | 0.29 [0.21, 5.58, 72.75] | 1.9 % | 3.7 % |
| hidden alley `prefer` | tile | 2 / 17 / 34 | 0.29 [0.21, 12.31, 139.63] | 0.2 % | 0.2 % |

An ask whose answer is waiting in the port is a read (0.3 us). The long asks are a
pull's first ones (a core asks before the X280 has answers ready: the 95th percentile
of 12 to 14 us on Sponza's count and place) and `prefer`'s choosing (3.4 us a choice,
asks queued behind it: up to 135 us). Where asking matters: hidden alley's count pull,
where ranges of 15.7 us wait 10.5 us for each answer (138 ns an answer from the X280 for
70,267 ranges in 9.67 ms) and half the command is asking. Where it does not: every tile
pull (0.1 to 0.6 %), and the place pull (2 to 4 %).

## The place pull taken apart

Sponza `textured`, `order` (ms a frame; a core's median / most; three runs, 15 frames
each):

| part | Sponza | hidden alley (`prefer`) |
|---|---|---|
| the X280's place phase | 1.899 | 14.388 |
| exchanges (ranges) a frame, a core | 2,049; 18 | 70,267; 587 |
| mover A asking | 0.035 / 0.043 | 0.514 / 0.895 |
| mover A waiting for its own thread to end | 0.235 / 1.186 | 0.829 / 1.642 |
| the positions page's and slices' read (116 KB a core) | 0.227 / 0.235 | 0.229 / 0.236 |
| the list writes: 128-byte writes a core | 2,446 | 21,374 |
| the integer mover waiting for the compute side's pages | 0.254 / 0.427 | 9.909 / 10.069 |
| the integer mover's whole share (read, waits, writes) | 0.768 / 1.838 | 13.538 / 14.026 |
| compute (pack) in place threads, the set-up pass | 0.719 / 1.262 | 13.471 / 13.852 |
| triangle and shade blocks read a core | 188 KB | 6,441 KB |
| a core's span | 0.803 / 1.878 | 13.882 / 14.360 |
| the cores' median last end; the tail after it | 0.801; 1.074 | 13.879; 0.478 |
| the longest range; when it started | 1.258; 0.042 after the first ask | 0.861; 3.189 |

The threads' place pull runs the set-up pass over every triangle block (compute) and
writes each record into the lists of every tile its box reaches (the integer mover).
In the stage-wise frame the set-up pass is the work that writes the lists (`setup.0`,
`setup.1`, in the tables' set-up column); its place commands (0.34 ms) are the rest.
The like comparison is the threads' place pull against the stage-wise place
and set-up together: Sponza 1.90 against 1.86 ms, hidden alley 14.39 against 13.34 ms
(8 % more), lynxsdesign 13.13 against 11.98 ms.

On Sponza a core's share is 0.80 ms: the positions read 0.23 ms at its first range,
0.25 ms waiting for compute, the rest the list writes and the ranges' own blocks. The
pull lasts 1.90 ms because of its tail: one core holds a range of 1.26 ms that started
0.04 ms after the first ask, and its last thread ends 1.07 ms after the cores' median.
On hidden alley the pull is the set-up pass: the integer mover waits 9.9 of 13.9 ms for
the compute side, whose pack CPU is busy 13.5 ms.

## Each CPU by step inside a tile thread

The ms a frame a core each compute CPU spends in each step (`order`; the cores'
median / most). `textured`'s steps are visibility, material, post; `lit`'s visibility,
material, light, post.

| scene, preset | CPU | in threads | visibility | material | light | post |
|---|---|---|---|---|---|---|
| Sponza, textured | unpack | 8.86 / 10.46 | 2.70 / 3.22 | 6.16 / 7.29 | - | 0.00 |
| Sponza, textured | math | 7.81 / 9.38 | 2.55 / 3.11 | 5.25 / 6.34 | - | 0.00 |
| Sponza, textured | pack | 8.91 / 10.51 | 2.78 / 3.29 | 6.09 / 7.22 | - | 0.05 / 0.06 |
| Sponza, lit | unpack | 10.58 / 11.79 | 2.69 / 3.49 | 4.99 / 5.79 | 2.93 / 3.38 | 0.00 |
| Sponza, lit | math | 4.59 / 6.16 | 2.55 / 3.38 | 2.03 / 2.93 | 0.00 | 0.00 |
| Sponza, lit | pack | 10.63 / 11.84 | 2.77 / 3.55 | 4.91 / 5.72 | 2.93 / 3.37 | 0.05 / 0.06 |
| hidden alley, textured | unpack | 23.24 / 51.44 | 9.47 / 20.33 | 13.92 / 31.09 | - | 0.00 |
| hidden alley, textured | math | 22.45 / 50.78 | 9.40 / 20.28 | 13.15 / 30.65 | - | 0.00 |
| hidden alley, textured | pack | 23.29 / 51.49 | 9.55 / 20.37 | 13.85 / 31.04 | - | 0.05 / 0.09 |
| hidden alley, lit | unpack | 23.51 / 35.03 | 9.60 / 20.30 | 9.85 / 11.81 | 4.25 / 5.94 | 0.00 |
| hidden alley, lit | math | 16.48 / 29.92 | 9.54 / 20.27 | 6.92 / 9.52 | 0.00 | 0.00 |
| hidden alley, lit | pack | 23.57 / 35.06 | 9.67 / 20.36 | 9.78 / 11.74 | 4.25 / 5.94 | 0.05 / 0.07 |
| lynxsdesign, lit | pack | 20.21 / 23.97 | 7.24 / 11.09 | 7.62 / 8.94 | 5.40 / 7.04 | 0.05 / 0.06 |
| classroom, textured | pack | 10.08 / 21.40 | 3.81 / 8.60 | 6.26 / 12.77 | - | 0.05 / 0.07 |

The tile pull's span on a core is 9.11 ms (`textured`) and 10.82 ms (`lit`). Unpack and
pack are busy 97 to 98 % of it in both; math 86 % (`textured`) and 42 % (`lit`). The
material step is 68 to 70 % of a tile thread in `textured`, 46 % in `lit`.

The stage-wise passes' counters (`stages/raster/kernels/passes/counters.hpp`, adapted
into the material step) are kept in the step's own state on pack and never leave the
core: no profile word of theirs is written. They give, inside one step, the counts of
its inner work; they do not give a step's time or its share. The step times here come
from the account, around each step's call.

## The X280 side

The tile pull's choosing function on the frame's X280 thread (the last frame's tile
pull of each run; 2,160 calls: 2,040 answers and one "none left" a core):

| scene, preset | way | us a call | ms a frame | its share of the tile pull | answers a core (least / median / most) |
|---|---|---:|---:|---:|---|
| Sponza, textured | kept | 0.38 | 0.83 | 4 % | 12 / 16 / 32 |
| Sponza, textured | order | 0.42 | 0.90 | 8 % | 11 / 17 / 23 |
| Sponza, textured | prefer | 3.41 | 7.37 | 74 % | 9 / 15 / 35 |
| Sponza, lit | prefer | 3.39 | 7.32 | 65 % | 14 / 17 / 20 |
| hidden alley, textured | order | 0.42 | 0.91 | 2 % | 5 / 16 / 32 |
| hidden alley, textured | prefer | 3.33 | 7.18 | 19 % | 2 / 17 / 34 |
| lynxsdesign, textured | prefer | 3.33 | 7.19 | 32 % | 3 / 16 / 46 |
| classroom, textured | prefer | 3.36 | 7.26 | 39 % | 3 / 15 / 34 |

`prefer` scans the slices for each answer: its choosing takes three quarters of the
tile pull's time on the X280 on Sponza. The cores feel it as a longer ask (`prefer` A ask
0.049 ms a frame against `order`'s 0.014, the 95th percentile of an ask 12.6 us
against 4.4 us), not yet as a longer frame. The count and place pulls are answered by
Komorebi's pull itself (no choosing function); their exchanges are the threads above
(2,049 a pull on Sponza, 70,267 on hidden alley, where an answer of the count pull
waits 10.5 us at the median: 70,267 answers in the 9.67 ms phase are 138 ns an
answer, as fast as the 120 cores ask for 16-us ranges).

`kept` gives each core its own slices: 136 slices over 120 cores leave 16 cores with
two (32 records against 16), so `kept`'s tile pull is about twice `order`'s on every
scene (Sponza 20.24 against 10.65 ms).

## A record a thread (for a waterfall)

What the records give, `order`, Sponza (us; median [5th, 95th percentile, most]):

| pull | threads a frame | ask to answer | answer to start | a thread |
|---|---:|---|---|---|
| count | 2,049 | 0.30 [0.22, 12.83, 23.97] | 0.82 [0.80, 0.86, 0.93] | 33 [11, 111, 659] |
| place | 2,049 | 0.30 [0.22, 13.86, 31.14] | 0.82 [0.80, 0.87, 0.93] | 72 [20, 170, 1,718] |
| tile | 2,040 | 0.30 [0.21, 4.35, 28.19] | 1.36 [1.33, 1.45, 105.20] | 666 [253, 1,468, 3,501] |

A thread's end is the later of mover B's end and pack's last step; mover A marks a tile
thread's end only when it next looks (about 100 us later), so mover A's mark is not the
end. A ring of 512 records a core holds Sponza's frame (6,138 threads); the artists'
scenes have 70,000 count and 70,000 place ranges a frame (about 585 a core a pull), and
a ring of 512 loses the frame's first threads (the blocks are whole): a waterfall of
them needs `account` of 1,300 or more. One run, hidden alley, `textured`, `prefer`,
`account` 2,048, 4 frames: no record lost, frame 60.99 ms (prefer with 512: 61.90):

| pull | threads a frame | ask to answer | answer to start | a thread |
|---|---:|---|---|---|
| count | 70,267 | 10.46 [0.29, 11.09, 23.72] | 0.85 [0.83, 0.88, 0.93] | 15.7 [11.1, 37.0, 453] |
| place | 70,267 | 0.29 [0.21, 4.74, 71.66] | 0.84 [0.82, 0.86, 0.94] | 39.5 [17.5, 97.6, 872] |
| tile | 2,040 | 0.29 [0.21, 13.36, 132.54] | 1.39 [1.36, 1.48, 109.00] | 798 [207, 4,922, 34,537] |

A record's words (`frame/kernels/frame.h` FX_R_*): the view (low 16 bits) and the pull
(high 16), the number, the ask, the answer, the start, mover A's and mover B's ends,
the cost told, then pack's end of each step of a tile thread (0 for a step not run).

## What the account suggests (not made)

Each with the number that suggests it; none was tried.

- The frame is lost in the TILE pull, not in place. Against the stage-wise fill, shade,
  (light,) show and push: hidden alley `textured` 37.5 (`prefer`) and 51.5 ms (`order`)
  against 28.3; `lit` 25.0 and 35.7 against 32.4; lynxsdesign `textured` 22.3 and 27.8
  against 20.3; Sponza `textured` 9.9 and 10.6 against 11.2. On hidden alley one tile
  thread of 34.5 ms ends the pull while a core's median span is 24.5 ms: the threads'
  host cuts no tile (`heavy` 0), the stage-wise frame cuts every tile above 0.33 of a
  core's mean cost into bands (`heavy`, `cut` of its middle pass). Cut at a weight from
  the frame's data (above), hidden alley `textured` `prefer` is 53.66 ms against the
  stage-wise 53.54; the cut's work in the sums phase (0.9 to 2.6 ms) then costs more
  than it gives where no tile ended the pull. A threshold that follows the frame's
  data on the card is not in the threads' form.
- The place pull is the stage-wise place and set-up together, 2 to 10 % more
  (hidden alley 14.39 against 13.34 ms): the set-up pass (compute busy 13.5 ms; the
  integer mover waits 9.9 ms for it). The count and place pulls read every triangle
  block twice (647.6 MB each on hidden alley).
- The count pull's answers on the artists' scenes: mover A waits 4.5 of 9.4 ms for
  them; a range of four blocks lasts 15.7 us and its answer waits 10.5 us. Fewer, larger
  ranges (`range_blocks`) would ask less often.
- `prefer`'s choosing: 3.3 to 3.4 us a call, 7.2 to 7.4 ms of the X280 a frame; 74 % of
  Sponza's tile pull already. At a shorter tile pull it, not the cores, would end it.
- One heavy tile thread ends hidden alley's tile pull (34.5 ms of 37.5; the cores'
  median 24.5): the preset's `heavy` is 0, so no tile is cut into bands.
- `kept` with 136 slices on 120 cores: 16 cores take twice the work; the tile pull is
  twice `order`'s.
- One place range of 1.72 ms ends Sponza's place pull (1.90 ms; a core's median 0.80).
- Mover A notes a tile thread's end about 100 us late (it looks when it next waits), so
  the cost it tells the X280 is long by as much.

## What is not measured

- A sun's DEPTH views: the frames here draw none (above); their phases apart are not
  in these tables.
- `gi`: not measured in this set.
- The scenes: Sponza and the scenes the threads' frame was proven equal on (hidden
  alley, lynxsdesign, and classroom for three layers); the other public scenes were not
  run.
- The X280's time an answer for the count and place pulls: they are answered by
  Komorebi's pull, which is not changed and keeps no such count; what a core sees of it
  (ask to answer) is above.
- The X280's choice words are read after the stop: the last frame's tile pull of each
  run, not every frame's.
- Komorebi's trace is loaded only for the waits above (512 commands a core); it gives
  each command's taking and end on a core, the threads inside come from the records.
  Both use the cores' 32-bit wall clock, which turns over every 3.18 s: the reading
  makes each frame's times signed around its first record.
- The texture pages and the light's pages are counted together as "asked".
- The stage-wise frames have no account here; theirs is `measurements/account/`.
