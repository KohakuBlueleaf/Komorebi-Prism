# The frame as threads

In the threads' presets (`textured_threads`, `lit_threads`, `gi_threads`) a view is not
a list of commands run one after another on every core. It is work cut into threads,
and every Tensix core takes threads one at a time from a thread on the card's X280
cores until none is left. The core that takes a tile's thread runs every step of that
tile: visibility, material, light and display, with the tile's planes kept in its own
memory between the steps. This page says what the threads are, who hands them out and
what a core keeps. How the renderer's parts fit is in [the renderer](renderer.md); how
the dispatcher and the handler work inside is in
[dispatch](../internals/program/dispatch.md), [work](../internals/program/work.md) and
[steps](../internals/program/steps.md).

Two kinds of thing are called a thread here, as in the code:

- **The threads of a view's work**, which the Tensix cores take: a count range, a place
  range, or a tile thread. Each is a number handed to a core by a **pull**.
- **The X280 threads** (Komorebi's threads: C on the card's X280 cores) that hand them
  out or run beside them: **the frame's thread** on work cluster 1, and in `gi_threads`
  **the job thread** on work clusters 2 and 3.

## Where each part runs

| part | what it does | where it runs |
|---|---|---|
| the frame's thread | serves FRAME and `sun`; for each view runs the four phases below and hands out every pull's numbers | X280 work cluster 1, its four cores (`prism.core.unit.FRAMES`) |
| the handler `work` | takes threads of the command's pull from its X280 core and runs each to its end | every Tensix core of the view's group, one program |
| the kinds `count` and `place` | a range of a layer's triangle blocks: counted, then placed into the lists | the Tensix core that takes the range |
| the sums (`RasterSums.sums`) | an ordinary command: each core takes the slices of its rank and writes their records and words | every Tensix core of the group |
| the running sum, the steps' words, the tile pull's choice | between the pulls: each layer's place a slice, each step's words of the frame's page, the next tile thread for a core that asks | the frame's thread |
| the tile thread | the steps of one tile (or one band of a tile's rows): visibility, material, light, display | the Tensix core that takes it |
| the field's update (`gi_threads`) | a graph kept on the card: the job thread's sources, passes and finish, the transport's applies on the lowest ranks, the new field handed to the frame's thread | the job thread on X280 work clusters 2 and 3; the applies on Tensix cores |

The host takes no part in a frame. It writes the camera, sends FRAME, and reads the
display's pages after the frame's event (`push` is false in the threads' presets: the
post step writes each tile's display page from the cores).

## A view in four phases

`dp_view` (`src/prism/program/dispatch/c/dispatch_view.c`) runs a view as four phases,
each one command on the view's group with the frame's page (the view, its layers, the
grid, the camera's address, the steps' words) as the command's block:

| phase | the command | the numbers handed out | what a core does with one | what it leaves |
|---|---|---|---|---|
| count | `work`, pull `TP_COUNT` | the view's count ranges: every layer's triangle blocks in ranges of `range_blocks` (4 by default; a block is 32 triangles) | counts each triangle into the tiles its box reaches; a core's counts and row histograms a layer | a counts page and a rows page a core and a layer |
| sums | `sums` | none: each core takes the slices of its rank | a slice's totals, a heavy tile's bands, its records in order of weight, its words, every core's positions | the records (a tile thread's each) and the slices' words |
| place | `work`, pull `TP_PLACE` | the same ranges, each to the core that counted it (the count pull's log replayed) | the set-up pass over the range's blocks; each record written into the lists of every tile its box reaches, one 128-byte write an entry | each layer's lists |
| tile | `work`, pull `TP_TILE` | the tile threads: a slice's records, `TR_NUMBER(slice, place)` | the tile thread's steps, in order | the tile's display page (a COLOUR view) or its 1/z page (a DEPTH view) |

Between the phases the frame's thread does what the next one needs. After the sums it
reads the slices' words, writes each layer's place into each slice (the running sum
over the slices of their entries), checks every layer's entries against its list slots
and gives the slices to the tile pull's choice. Before the tile pull it fills each
step's words of the frame's page (`dp_frame_words`, each step's `<step>_frame_words` in
the steps' order). The phases a view runs are the number `dispatch_phases` (0: all of
them).

A **slice** is a run of 16 tiles along a row of the frame's grid (`SLICE_TILES`), and a
slice holds at most 32 records (`TR_SLICE_RECORDS`). A **record** is a tile thread: a
whole tile, or a band of a tile's rows when the tile's entries over every layer pass the
weight `heavy`; it names the tile, its rows, its weight, the page it writes and, for each
layer, its first list slot and its entries (`src/prism/core/include/thread/record.h`).
A frame of 1,920 x 1,080 is 60 x 34 tiles of 32 x 32 pixels, 136 slices.

## The kinds: count and place

`prism.stages.raster.threads.kinds` gives the geometry's two kinds of thread beside the
tile thread. Each names its pull, its header (`<name>_movers` for both movers,
`<name>_compute` for the compute CPUs, `<name>_end` when the pull ends), its rings and the
state it keeps on a core during its pull:

| kind | pull | keeps on a core | streams |
|---|---|---|---|
| `count` | `TP_COUNT` | the counts (a word a tile) and the row histograms (64 bytes a tile) of the capacity's tiles | the triangle blocks |
| `place` | `TP_PLACE` | the positions (a slice's tile words, then its band entries) and the slices' places | the triangle blocks and the shade blocks |

The place pull hands each core the ranges it counted, in the order it counted them, so a
core's entries in a tile's list follow its own count. Inside an item's list the cores'
entries follow each other by rank.

## The tile thread and its steps

A pipeline's tile thread is its steps in order and the planes they share
(`prism.core.thread.module.TileThread`), named by the preset's option `tile_thread`
(`src/prism/program/threads/tiles.py`):

| tile thread | presets | steps | planes |
|---|---|---|---|
| `TEXTURED` | `textured_threads` | `visibility`, `material`, `post` | `frame.visibility` |
| `LIT` | `lit_threads`, `gi_threads` (`GI` is `LIT`) | `visibility`, `material_lit`, `light`, `post`, `depth_out` | `frame.visibility`, `frame.surface` |

| step | given by | what it does with the tile | in a COLOUR view | in a DEPTH view |
|---|---|---|---|---|
| `visibility` | `stages/raster/steps` | walks every layer's list as it streams and fills each layer's planes (1/z, red, green, blue, the triangle number), equal depths going to the lower triangle number | yes | yes |
| `material` | `stages/material/texture/steps` | walks the layers' lists again in SHADE's order (opaque, masked, glass), asks for texture pages, leaves the colour | yes | no |
| `material_lit` | the same | as `material`, leaving the surfaces (two frames of ten planes) for the light | yes | yes |
| `light` | `stages/direct/light/steps` | the surface and visibility planes into the colour planes; asks for light pages (the shadow map's, the field's) | yes | no |
| `post` | `stages/post/show/steps` | pushes the colour planes as an output block, which the mover that takes it converts by SHOW's rule and writes to the tile's display page | yes | no |
| `depth_out` | `stages/raster/steps/depth` | pushes the 1/z plane as an output block, written row-major to the tile's page of the view's target | no | yes |

A step's compute (`<name>_compute`) runs on the three compute CPUs, which split the work
among themselves. A list pass is streamed to them by the movers after the passes of the
steps before; a page a step asks for is read into L1 by a mover; an output block is
converted and written by the mover that takes it. A step with `begin` runs
`<name>_begin` once a command, before its first thread.

## Who hands out what

Every Tensix core has a port on one of the frame cluster's four X280 cores
(`program.ports`: a quarter of the cores each, so a core's index at its port is its
rank; 30 cores a port on 120). A core's mover A asks its port for the next number and
hands the thread to the compute CPUs and to mover B; when the pull has nothing left it
answers "none left" and the core's part of the command ends.

| pull | handed out by | how |
|---|---|---|
| count | Komorebi's pull with a log (`KMX_PULL_LOG`) | the next range to whichever core asks; the log keeps which core took which |
| place | Komorebi's pull replaying that log (`KMX_PULL_REPLAY`) | each core its own ranges again |
| tile | Komorebi's pull with a choosing function (`dp_choose`) | the next record for the core that asks, by the policy below, with a word: a code (0, the resident code) and a hint |

The tile pull's policy is the frame host's option `policy`
(`src/prism/program/dispatch/c/dispatch_choose.h`):

| policy | the answer |
|---|---|
| `prefer` (the default) | a slice within `near` slices (1 by default) of the core's last slice, heaviest record first; else any slice with records left. An answer near the last slice carries the hint `TA_HINT_NEAR`: the core's pages may still be held |
| `order` | the slices in order, each slice's records in order |
| `kept` | slice `s` to the rank `s mod` the group's cores, kept |

With every ask a core tells the cost of the thread that ended and the codes it holds; the
choice keeps a few words a core and a slice in the frame cluster's memory and never waits.

## What a core keeps

The handler `work`'s memory on a core holds, past its shared line, either the tile
thread's part or a kind's, over the same bytes (`prism.program.frame.generate.memory_of`):

| what | kept for | its size |
|---|---|---|
| the planes (`frame.visibility`; with `LIT` also `frame.surface`) | one tile thread: left by a step, read by the steps after it | `frame.visibility` 20 float32 tiles (five planes for each of up to four layers); `frame.surface` 20 more |
| each step's `keeps` | across the tile threads of a command (e.g. the material step's page cache of 128 texture pages and a white one, its work; the light step's table, pages and work; the post step's table) | sized by each step, some by the capacity held |
| each kind's `keeps` | across the ranges of its pull | by the capacity's tiles and slices |

The light step asks for its pages into the material step's page cache, so a texture or
light page a core read for one tile thread may serve the next one; the `prefer` policy's
near answers give a core tiles next to its last. Nothing of the planes is written to the
card's memory between the steps: a tile's display page (or its 1/z page) is the only
thing a tile thread writes.

## The frame's thread on the X280

The frame's thread is the director's runtime (`src/prism/program/director/c/`) with a
sequence generated for the pulls (`prism.program.dispatch.generate`): `dr_view` is the
dispatcher's view, then each unit's frame work. In the threads' presets no unit has
frame work of its own; the units give the dispatcher the numbers, columns and regions
the steps' frame words read (`src/prism/program/threads/units.py`). It serves:

| thread command | what it does |
|---|---|
| FRAME | the units' setup once, then the eye's view (view 0, COLOUR) as the four phases; its times row |
| `sun` (`direct.shadow_pcf`) | one DEPTH view a quadrant of the sun's shadow map, each as the four phases |
| `job_wants` (`gi_threads`) | from the field's graph, between two of the frame's commands: the cores an update wants, and a field just made (its half of the field's pages and its scale) |

While an update wants cores, a view's group starts above them (`jobs_unit_frame_first`):
the frame's pulls take the other ranks, and a view that would be left no core stops with
`DP_NO_CORES`, the cores wanted in its result. Each phase has a progress mark
(`DP_WHERE_*`) and a give-up (`DP_LATE_COUNT`, `DP_LATE_PLACE`, `DP_LATE_TILE`) within
the director's wait limit; the first code that is not 0 ends the view.

## The views

A **view** is what a run of the phases draws: its index, its kind, its camera, its grid
and, for a DEPTH view, its target.

| view | kind | sent by | the tile thread's steps | written |
|---|---|---|---|---|
| 0, the eye's | COLOUR | FRAME | the steps marked `colour` | the display (`display.picture`) |
| 1 to n, the sun's quadrants | DEPTH | `sun`, after the sun moves | the steps marked `depth`: `visibility`, `material_lit` (the masked layer's cut), `depth_out` | the quadrant's pages of the shadow map (`light.shadow_map`) |

A DEPTH view draws only the layers whose depth column is set (the opaque and masked
ones). The sun's views have their own lists, sized for the quadrants' cameras
([direct.shadow_pcf](../../src/prism/stages/direct/shadow_pcf/README.md)).

## When lists are too small

The lists a load holds are sized on the host for the eye's camera at load, with a
quarter more (`LIST_MARGIN` 1.25). A camera that sees more entries than a layer's list
slots stops its view after the running sum, before any list is written:

| code | when | what happens |
|---|---|---|
| `DP_LISTS_SMALL` | a layer's entries over the slices pass its list slots | the frame's thread copies the need page (the view, its kind, each layer's entries); the host gives each layer past its slots lists of its entries and a quarter more while the run stays loaded, writes its row in every view again, and the frame is tried again (`retries` in the record) |
| `DP_TOO_MANY` | the view's ranges or slices pass the dispatcher's capacity (a larger frame) | one reload with what it needed (`reloads` in the record) |
| `DP_NO_CORES` | an update holds every core | the view is refused, the cores wanted in its result |

The slots a layer grew to are kept in the option `list_slots_least` for a later load.

## The frame host's options

`prism.program.threads.host.ThreadsHost` reads:

| option | default | what it sets |
|---|---|---|
| `cores` | every rank | the view's group |
| `range_blocks` | 4 | triangle blocks a count range |
| `policy` | `prefer` | the tile pull's choice |
| `near` | 1 | the slices a near answer may be away |
| `heavy` | 0 (never) | the weight over every layer past which a tile is cut into bands, `ceil(weight / heavy)` of them |
| `list_slots_least` | 0 | a layer's least list slots (a number, or a dict by layer name) |
| `account` | 0 (built without it) | the records a core's account page holds |

## Measured

On one P150A at 1,920 x 1,080 the threads' frame with `prefer` is 13.134 ms on Sponza's
overview (`textured`) against the stage-wise frame's 16.428 ms; on the artists' scenes
it is faster than the stage-wise frame in `lit` and slower in `textured`; on hidden
alley one heavy tile thread of 34.5 ms ends the tile pull (`heavy` 0 cuts none). Every
phase, the four ways of
handing out, the bytes by path, a core's waits and the X280's choice are in
[the account](../performance/account.md), from
[measurements/threads_account](../../measurements/threads_account/README.md).
