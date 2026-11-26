# The stage-wise form's thread: the director

The presets without `_threads` in their names (`raster`, `textured`, `lit`, `gi`, and
`lit_tile`, `gi_tile`) run a frame as the stage-wise form: the frame's thread sends each
stage's commands one after another, every core taking each command, and waits for each.
Their pictures are the ones the threads' presets are compared with. `prism.program.form`
chooses the form once, when the pipeline is assembled: the threads' form when an
implementation's host has `threads` true, else this one. The threads' form runs on the
same runtime, with the dispatcher in place of the units' sequence
([the dispatcher](dispatch.md)).

The code: `src/prism/program/director/` (`c/director.h`, `c/director.c` the runtime,
`generate.py` the generated sequence, `thread.py` the thread declared), the layout
`src/prism/core/resources.py` and a unit's contract `src/prism/core/unit.py`.

## Units and the generated sequence

An implementation's part of the thread is a unit (`Unit`): its C, the functions it gives
(`<name>_unit_setup`, `_layer`, `_frame`, one a served command), the slots it gives and
takes, and what it asks for (regions, numbers, layer columns, times, results, build
defines, its work cluster). The layout (`resources.Layout`) assigns every region, number,
column, time and result a place and writes them into the generated header; nothing in
the runtime names a stage.

`generate.py` writes `pipeline.c`:

- `dr_units_setup`: each unit's setup, once, at the first frame;
- `dr_view`: unit by unit in the pipeline's order, its `layer` role for each layer of the
  view (in a DEPTH view only the layers whose `depth` column is set), then its `frame`
  role; the first code that is not 0 ends the view;
- `kmx_program`: the command switch: `frame`, each unit's served commands, and
  `core_step` when another cluster's units run.

A view (`dr_view_t`) is COLOUR (the eye's, view 0) or DEPTH (its product the nearest
surface's 1/z into its target: the sun's quadrants, views 1 on, built by the unit of
`direct.shadow_pcf`).

## Commands, waits and rows

A unit builds its stage's command with its class's builder and runs it with `dr_run`:

- `dr_submit` puts it in the ring, again while the ring is full, for `DR_WAIT_TICKS` (one
  second of the X280's timer) at most (`DR_RING` after).
- `dr_wait` waits for its event within the same second from its first submit. A command
  rejected busy (another source's command held the slot) is submitted again at the
  dispatcher's next wake, for up to `DR_LINES_HELD` (8) commands in flight; the times row's
  `resubmits`, `wake_ticks` and `wake_most` count them. `DR_COMMAND` for a command that did
  not finish.
- On work cluster 2 (the units of the field's update in `gi_tile`, the option
  `update_beside`), a core command goes to the frame's director as a `core_step`, which
  runs it between two of its commands and answers its code and its ticks; up to
  `DR_STEPS_HELD` (8) in flight.

Each `frame` command, and each served command that runs views, writes a times row: the
frame's ticks, the code, its number, the view and layer reached, and each unit's times
and results; the last 256 rows are kept (`TIMES_ROWS`). The FRAME command's event carries
one result word, the code; the rows and regions are read after the stop.

Codes: 0, the runtime's (`DR_BAD_ARGS`, `DR_RING`, `DR_COMMAND`, `DR_PARALLEL`), or a
unit's above `DR_UNIT_CODES` (16).

## Against the threads' form

| | stage-wise | threads |
|---|---|---|
| a view | each stage's commands on every core, one after another | four pulls and the sums |
| which core does what | the commands' own split (the raster stage's middle pass deals items to fill cores by cost) | a core takes the next thread when it is done with the last |
| a tile between stages | written to DRAM by one command, read by the next | kept in the core's memory between the steps |
| heavy tiles | cut by the middle pass each frame (tiles past 0.33 of a core's mean cost) | cut past the option `heavy` (0: never) |
| lists too small | the frame stops; the loop reloads with more | the dispatcher writes its need; the lists grow while the run stays loaded |

The raster stage's stage-wise passes and its middle pass are
[the raster model](../raster/model.md); the measured frames of both forms are
[the frame's time](../../performance/frames.md).
