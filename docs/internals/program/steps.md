# Steps, kinds and the tile thread

What a stage gives the threads' form: a **step** of the tile thread, or a **kind** of
thread beside it, each a module (its header, its planes, its passes, its rings, its kept
state); the pipeline's **tile thread** is its steps in order. `prism.program.frame`
composes them into the handler `work` ([the handler `work`](work.md)) and the dispatcher
hands their threads out ([the dispatcher](dispatch.md)). The contract is
`src/prism/core/thread/module.py`.

## The parts of the contract

| part | fields | meaning |
|---|---|---|
| `Plane` | name, format, tiles | a plane of a tile kept in the core's memory while its thread runs, named by a slot |
| `ListPass` | layers, block records, record bytes, page records | one pass over the tile's lists: the layers in the order it walks them (a function of the frame's layer names), streamed to the compute CPUs after the passes of the steps before |
| `Output` | name, block bytes, blocks, convert | a stream of blocks the step pushes for the movers to write; `convert` the function a mover runs on a block's payload before it writes it |
| `Step` | below | a step of the tile thread |
| `Kind` | name, pull, header, keeps, buffers, fields, streams | a kind of thread beside the tile thread: the pull it runs in (`TP_COUNT`, `TP_PLACE`), its header giving `<name>_movers(ctx, range)`, `<name>_compute(ctx, range)` and `<name>_end(ctx)` |
| `TileThread` | steps, planes | the pipeline's tile thread |

A `Step`'s fields:

| field | meaning |
|---|---|
| `name`, `header` | its header (from `src/prism/`) gives `<name>_compute(ctx, tile, planes)` for the three compute CPUs, which share the work among themselves |
| `passes` | its list passes |
| `requests` | the page kinds it asks the movers for |
| `outputs` | the output streams it pushes |
| `reads`, `leaves` | the planes it reads, the planes it leaves for the steps after it |
| `keeps` | state kept on the core across threads, `{name: bytes}` (a number, or a function of the capacity held) |
| `buffers` | rings of its own, `{name: (pages, page bytes, the CPU that pushes)}`: raw words; with a fourth element, a Komorebi format (`km.bf16`, `km.bfp8_b`, ...), a typed ring whose page is one tile of that format, as the matrix engine's unpack and pack take it (`field_of` makes `km.L1[format, pages, 32, 32]` without `raw`); the page bytes must equal the format's tile |
| `streams` | the rings of `buffers` Komorebi's movers move |
| `words`, `thread` | its words of the frame's page, filled by `<name>_frame_words` in the C file `thread`, on the frame's thread, once a view |
| `codes` | variants of its compute by the tile pull's code (0 is the resident one) |
| `colour`, `depth` | whether a COLOUR and a DEPTH view's tile thread runs it |
| `begin` | whether its header gives `<name>_begin(ctx)`, run once a command on mover A before its first thread |
| `fields` | the common fields (`prism.core.fields`) its code uses |

`TileThread.check` refuses a plane or a step named twice, a step naming a plane that is
not the thread's, a step reading a plane no step before it leaves, and a ring pushed by no
CPU of a core. `compose` refuses, with the names: two kinds of one pull, a name that is a
step's and a kind's, an output named twice, list passes of different geometry, more steps
than the account holds (`FX_STEPS` - 1), the steps' words past the page, a layer that is
not the frame's.

## The composition

`generate.compose(thread, kinds, layers, held, account)` gives a `Composition`:

- the steps' words: `PRISM_TF_<STEP>_<WORD>` from `TF_STEP_AT`, one source for the kernels
  and the frame's thread;
- the planes' places, each on 64 bytes;
- the kept state's places: the steps' end to end, then the planes; each kind's over the
  same bytes;
- each step's passes as layer indices, and each view's list stream: the passes of the
  COLOUR view's steps one after another, and of the DEPTH view's;
- the rings: the handler's own, each output's pair, each step's and kind's (a ring two
  kinds declare alike is one field `kind_<name>`), the stream halves first;
- the handler's memory: the shared line, the account's part when built, and the largest
  of the tile thread's part and each kind's;
- the codes held, a bit a code, which a core tells with its asks.

## Today's tile threads

`src/prism/program/threads/tiles.py`:

| tile thread | steps in order (COLOUR view) | DEPTH view | planes | preset |
|---|---|---|---|---|
| `TEXTURED` | visibility, material, post | (no DEPTH view) | `frame.visibility` | `textured_threads` |
| `LIT` | visibility, material_lit, light, post | visibility, material_lit, depth_out | `frame.visibility`, `frame.surface` | `lit_threads` |
| `GI` | as `LIT` (the field's update is the job thread's) | as `LIT` | as `LIT` | `gi_threads` |

The steps:

| step | stage | what it does in a tile thread | passes, requests, outputs | planes read / left | kept state | words | begin |
|---|---|---|---|---|---|---|---|
| `visibility` | raster (`stages/raster/steps/`) | every layer's records walked as its list streams; each layer's five planes filled on pack with the tie-deciding row (equal depths to the lower triangle number) | a pass over every layer | - / `frame.visibility` | - | - | no |
| `material` | material.texture (`stages/material/texture/steps/`) | the layers in SHADE's order (opaque, masked, glass) walked again; texture pages asked a pass of rows at a time into the page cache; the colour into the first layer's planes | a pass in SHADE's order; asks `texture` | `frame.visibility` / `frame.visibility` | work, cache (128 page slots and the white page), run | layers, textures, table | the table |
| `material_lit` | material.texture | as `material`, writing the frame's words and the surfaces; in a DEPTH view only the masked layer's 1/z merged | as `material` | `frame.visibility` / `frame.visibility`, `frame.surface` | as `material`, the light work, the camera | layers, textures, table | the table, the camera |
| `light` | direct.light (`stages/direct/light/steps/`) | the surface and visibility planes lit a quarter tile at a time into the first layer's colour planes; light pages asked | asks `pages` | `frame.surface`, `frame.visibility` / `frame.visibility` | table, work, pages, pass | table, pages, glass, the field's first page, units and scale | the table with the camera, the field's version |
| `post` | post.show (`stages/post/show/steps/`) | the first layer's colour planes (a band: its rows) pushed as a block; a mover converts it by SHOW's rule and writes the tile's display page | output `display` | `frame.visibility` / - | table, scratch | table, pages | the thresholds and buckets |
| `depth_out` | raster (`stages/raster/steps/depth/`) | a DEPTH view's 1/z plane pushed as a block, turned row-major by a mover and written to the tile's page of the view's target | output `depth` | `frame.visibility` / - | scratch | pages | no |

In every step the pack CPU does the work; unpack hands the list blocks on and serves
pack's mails (`compute_mail`, the answers of its asks); the light and post steps give the
math CPU no part.

The kinds (`stages/raster/threads/kinds.py`):

| kind | pull | what a range does | kept state | rings |
|---|---|---|---|---|
| `count` | `TP_COUNT` | the range's triangle blocks through the projection pass; on the integer mover each kept box into the core's entries a tile and its row histograms | counts, rows (a word and 64 bytes a tile of the capacity) | the triangle block pair, out, the pass's spaces |
| `place` | `TP_PLACE` | the same ranges again through the set-up pass; on the integer mover each record to its list at the core's position of every tile or band it reaches | positions, the slices' places | the triangle and shade block pairs, out, the pass's spaces |

Between them the sums are an ordinary command of a class of its own (`RasterSums`), not a
kind.

## How a stage gives one

A stage's step is a declaration beside its stage-wise code (`steps/step.py`), a header
for the CPUs (`steps/kernels/`), and, when it has words, a C file for the frame's thread
(`thread/<step>_frame_words.c`). The post step, whole:

- `Step(name="post", header=".../post_step.hpp", outputs=(Output("display",
  kPostBlockBytes, 2, convert="post_convert"),), reads=("frame.visibility",),
  keeps={"table": ..., "scratch": ...}, words=("table", "pages"), thread=...,
  begin=True)`;
- `post_compute` on pack copies the band's rows of the three colour planes into an output
  block (`out_reserve`, `out_push`) for the tile's page; `post_begin` on mover A reads the
  thresholds from the regions' bank and makes the kept buckets; `post_convert` on the
  mover that takes a block converts it in place;
- `post_frame_words` writes the thresholds' address and the view's tiles into the page.

The stage's own host and its unit's numbers are reused: the threads' implementations
(`src/prism/program/threads/implementations.py`) register each stage under its own name
and `.threads` (`raster.threads`, `material.texture.threads`, `direct.light.threads`,
`direct.light.threads_field`, `post.show.threads`, `indirect.transport.threads`,
`indirect.field_update.threads`), with no class of their own and a unit that only gives
the numbers, columns and regions the steps' words read (`threads/units.py`). The frame's
own implementation (`raster.threads`, host `ThreadsHost`) writes `frame.visibility` and
`frame.lists`; `form_of` chooses the threads' form when an implementation's host has
`threads` true ([the stage-wise form's thread](director.md)).

The steps reuse their stage-wise kernels' parts: the fill's row, SHADE's keys and passes,
LIGHT's quarter tile and row, SHOW's conversion.

## Limits

- No step has variants by code, and no step reads the tile pull's hint; every answer's
  code is 0.
- A step's kept state lives for a command: its `begin` fills it again each command.
- A record holds four layers (`TR_LAYERS`).
