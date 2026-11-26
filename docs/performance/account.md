# The account of the threads' frame

Where the time and the bytes of a frame go when it is run as threads: the count, place
and tile pulls handed out by the frame's X280 thread, each core taking threads one by
one ([the dispatcher](../internals/program/dispatch.md),
[the handler `work`](../internals/program/work.md)). Every number is from
[measurements/threads_account](../../measurements/threads_account/README.md), which has
every table whole; this page gives what they say.

Conditions: one Blackhole P150A, 120 cores, AICLK 1,350 MHz; 2026-11-27 (UTC+8),
Komorebi 0.5.3; 1,920 x 1,080, the scene's camera (Sponza: `overview`), 16 frames a
load; a number is the median over frames 2 to 16 of a run, then the median of three runs
interleaved by way. Every frame code 0 and every picture equal to the stage-wise one.
Nothing was tuned: every constant is the preset's.

## What the account is

A build option of the threads' host (`account`, the records a core keeps; 0 builds
nothing of it), compiled into the handler `work` and the dispatcher:

- counters a command by (view, pull), in 1,024 bytes of the handler's memory: on each
  mover the threads taken, the cycles waiting for an answer (`ask`), for "none left"
  (`none`), for its own thread before asking the next (`ahead`), the drain, the
  command's span, the cycles running its share (`run`) and serving the compute side
  (`serve`), the bytes it moved by path; on each compute CPU the cycles in threads and in
  each step;
- a record a thread (64 bytes, one write to DRAM when the thread ends): the view and
  pull, its number, when it was asked for, answered, started, ended on each mover, the
  cost told to the X280, and pack's end of each step of a tile thread (`frame.h`
  `FX_R_*`); a ring of `account` records a core;
- on the X280 each core's answers, "none left" answers and the timer's ticks in the
  tile pull's choosing function.

Its cost: `order` on Sponza `textured`, 13.832 ms without it and 13.970 ms with it (+1.0 %;
most of it a count at each 128-byte list write of the place pull); on the artists' scenes
inside the runs' spread.

Every core time is the core's wall clock, the clock Komorebi's trace uses, so a record
and the trace's rows are on one axis; the 120 cores' first asks of a frame lie within
4.0 us of each other. The X280's times are durations of its timer at 50 MHz.

## The phases

ms; the stage-wise commands grouped: count the count passes, sums the sum and histogram
passes, running the middle pass, place and set-up the passes that write the lists, tile
the fill, shade, light, show and push. The threads' place pull runs the set-up pass and
the list writes together, so it stands against the stage-wise place and set-up together.

| scene, preset | way | frame | count | sums | running | place (+ set-up) | tile |
|---|---|---:|---:|---:|---:|---:|---:|
| Sponza, textured | stage-wise | 16.428 | 0.940 | 0.329 | 2.056 | 0.339 + 1.525 | 11.234 |
| Sponza, textured | `kept` | 23.405 | 1.040 | 0.271 | 0.048 | 1.799 | 20.243 |
| Sponza, textured | `order` | 13.901 | 1.041 | 0.271 | 0.049 | 1.806 | 10.647 |
| Sponza, textured | `prefer` | 13.134 | 1.041 | 0.271 | 0.049 | 1.802 | 9.930 |
| hidden alley, textured | stage-wise | 53.544 | 9.462 | 0.331 | 2.068 | 0.340 + 12.998 | 28.335 |
| hidden alley, textured | `order` | 75.836 | 9.668 | 0.270 | 0.051 | 14.244 | 51.477 |
| hidden alley, textured | `prefer` (account) | 61.899 | 9.678 | 0.271 | 0.051 | 14.384 | 37.505 |

The running sum on the X280 is 0.05 ms against the stage-wise middle pass's 2 ms. The
place pull is the stage-wise place and set-up together, 2 to 10 % more (hidden alley
14.39 against 13.34 ms). The frame is won or lost in the tile pull.

## Heavy tiles

The stage-wise frame cuts every tile past 0.33 of a core's mean cost into bands each
frame; the threads' host cuts none unless given `heavy`. With `heavy` from the frame's
data (0.33 x the frame's entries over every layer / 120 cores; Sponza 807, hidden alley
7,053, lynxsdesign 5,700, classroom 1,837):

| scene, preset | tiles cut / bands | `prefer`, heavy 0 | `prefer`, cut | sums, cut |
|---|---|---:|---:|---:|
| Sponza, textured | 34 / 70 | 13.134 | 14.016 | 1.214 |
| hidden alley, textured | 94 / 213 | 61.899 | 53.663 | 2.888 |
| hidden alley, lit | 94 / 213 | 49.396 | 52.119 | 2.888 |
| lynxsdesign, textured | 116 / 248 | 45.050 | 44.608 | 2.398 |
| classroom, textured | 23 / 89 | 23.469 | 18.687 | 2.031 |

The heaviest tile holds 2,261 entries on Sponza, 36,438 on hidden alley. Where one tile
thread set the tile pull's end (hidden alley `textured`, classroom) the cut wins; where
none did, the cut's work in the sums (0.9 to 2.6 ms) costs more than it gives. A cut at a
weight the card takes from the frame's own data is not in the threads' form.

## Bytes by path

MB a frame, all cores; the same in every way of handing out (the paths do not depend on
which core takes a thread):

| scene, preset | triangle blocks (count / place) | shade blocks | lists (place writes / tile reads) | texture and light pages asked | rows out |
|---|---|---:|---|---:|---:|
| Sponza, textured | 37.77 (18.88 / 18.88) | 4.20 | 121.05 (37.58 / 83.48) | 108.94 | 8.36 |
| Sponza, lit | 37.77 (18.88 / 18.88) | 4.20 | 121.05 (37.58 / 83.48) | 276.41 | 8.36 |
| hidden alley, textured | 1,295.15 (647.57 / 647.57) | 143.91 | 995.37 (328.31 / 667.06) | 95.14 | 8.36 |
| hidden alley, lit | 1,295.15 (647.57 / 647.57) | 143.91 | 995.37 (328.31 / 667.06) | 1,172.14 | 8.36 |

The triangle blocks are read twice (count, then place). The place pull writes each list
entry as one 128-byte write; the tile pull reads the lists once, for every step's passes
together. Between the steps of a tile nothing goes to DRAM: the rows out are the display.

## Where a core stands still

Core-ms a frame (120 cores together), from the records and Komorebi's trace of the same
runs (`textured`):

| wait | Sponza `order` | Sponza `prefer` | Sponza `kept` | hidden alley `prefer` |
|---|---:|---:|---:|---:|
| count: asked, not yet answered | 5.8 | 5.7 | 5.8 | 544.0 |
| count: end of pull | 47.2 | 47.4 | 47.3 | 2.4 |
| sums: end of the command | 27.3 | 27.3 | 27.3 | 27.3 |
| place: end of pull | 127.7 | 129.4 | 128.0 | 57.4 |
| tile: asked, not yet answered | 1.9 | 6.8 | 1.7 | 6.7 |
| tile: end of pull | 184.2 | 91.3 | 1,337.3 | 1,480.9 |
| the frame's thread between pulls (three gaps) | 13.4 | 13.4 | 13.2 | 31.8 |
| the frame on the cores | 1,658.5 | 1,572.3 | 2,817.6 | 7,406.7 |

A core stands still where a phase waits for its slowest core: on Sponza `order` 386 of
1,659 core-ms (23 %). On hidden alley the tile pull's end is almost all of it: one tile
thread of 34.5 ms ends the pull while a core's median span is 24.5 ms. `kept` gives each
core its own slices: 136 slices over 120 cores leave 16 cores with twice the work, and its
tile pull is about twice `order`'s.

## What asking costs

An ask whose answer waits in the port is a read: 0.3 us at the median. Its share of the
command on the cores: 0.2 to 0.6 % in every tile pull, 3.7 to 4.3 % in the place pulls,
8.6 % in Sponza's count pull, and 47.9 % in hidden alley's count pull, where ranges of
15.7 us wait 10.5 us for each answer (70,267 ranges in 9.67 ms: 138 ns an answer from
the X280). `prefer`'s choosing takes 3.3 to 3.4 us a call on the X280 (`order` 0.42,
`kept` 0.38), 7.2 to 7.4 ms of the X280 a frame: 74 % of Sponza's tile pull on the X280,
which the cores feel as a longer ask (95th percentile 12.6 us against `order`'s 4.4 us),
not as a longer frame.

## Inside a tile thread

ms a frame a core, the cores' median (`order`):

| scene, preset | CPU | in threads | visibility | material | light | post |
|---|---|---:|---:|---:|---:|---:|
| Sponza, textured | pack | 8.91 | 2.78 | 6.09 | - | 0.05 |
| Sponza, lit | pack | 10.63 | 2.77 | 4.91 | 2.93 | 0.05 |
| hidden alley, textured | pack | 23.29 | 9.55 | 13.85 | - | 0.05 |
| hidden alley, lit | pack | 23.57 | 9.67 | 9.78 | 4.25 | 0.05 |

Unpack and pack are busy 97 to 98 % of the tile pull's span on a core, math 86 %
(`textured`) and 42 % (`lit`). The material step is 68 to 70 % of a tile thread in
`textured`, 46 % in `lit`.

A thread's life on Sponza `order` (median, us): ask to answer 0.30 in every pull, answer
to start 0.82 (count, place) and 1.36 (tile), a thread 33 (count), 72 (place), 666 (tile).

## What is not measured

- A sun's DEPTH views (the runs send no `sun` command), and `gi_threads` with the account:
  its frame without the account, by phase, is in [gi_threads](gi_threads.md).
- Scenes other than Sponza, hidden alley, lynxsdesign and classroom.
- The X280's time an answer in the count and place pulls (Komorebi's pull keeps no such
  count); what a core sees of it is above.
- Mover A notes a tile thread's end when it next looks (about 100 us late), so the cost it
  tells the X280 is long by as much.
