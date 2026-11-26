# direct.light

The direct light of a lit frame: after the material stage's SHADE has written each
tile's surface (albedo, normal, visibility, specular, in two frames) and the raster's
frame holds each pixel's 1/z and material word, LIGHT turns every core's tiles into the
frame's colour planes: the sun with its shadow map's filter, the lamps, the specular
terms, the sky, the ambient or the indirect field, emissive and the background, then
the tone step. A scene with glass runs it twice: the linear colour C, then the glass
layer lit over C. With the build option `light_shows`, the last LIGHT of a colour view
also does the display stage's conversion: its mover B turns the colour planes it holds
into the display's 8-bit page of each tile, and no SHOW command follows.

## Files

| File | What it holds |
| --- | --- |
| `device.py` | `Light`, the class on the card: one handler `light`, a `km.kernel` handler; `LightShown`, with the option `light_shows`: one own field more, mover B's scratch pages; `made(host)` |
| `__init__.py` | the declaration (`LIGHT`), registered as `direct.light` |
| `host.py` | `LightHost`: the light pages, LIGHT's table and profile pages a surface; the texture stage's surfaces (slot `frame.surface`), LIGHT's words written into their directory pages once loaded (the table's, the profile's, the pages'); slots `light.shadow_map`, `light.field`; the field's scale taken from slot `light.field_scale` when a host gives it; the unit's numbers; the sun region's table, its one writer: written once loaded and again when the run's sun, the tone, the terms, the indirect switch or the field's scale change (controls `exposure`, `saturation`, `curve`, `term_<name>`, `indirect` with the term indirect); the command's words |
| `unit.py` | the thread unit (the frame role): its numbers (the surfaces' directories, 1 + the glass layer), the slots it takes, its times `light`, `light_glass`, the forms as defines (with `light_shows`, `DIRECT_LIGHT_SHOWN`) |
| `thread/direct_light_unit.c`, `.h` | a COLOUR view's LIGHT: displayed, or linear then glass with a glass layer, the last one with `kLightShown` under `light_shows`; none for a DEPTH view |
| `check/thread_frame.py` | the preset `lit`'s frames by a Loop: pictures against the reference's lit frame at the run's sun (the reference's moved lights, the map rebuilt), tone and terms, the sun's map, the sequence the times row shows, the times by layer; `lit`, the judge the display stage's check uses |
| `model/` | LIGHT's numbers (`numbers.py`, read from `kernels/light.h`, `core/include`'s `surface.h` and `texel_pages/protocol.h`, the texture stage's `shade.h`), its table, terms, pages, field, the sun's region, the surface and the checks' expectations, in numpy |
| `kernels/light.h` | LIGHT's table words, terms, an item's planes, the profile's words, the give-up places; it includes the texture stage's `shade.h` for SHADE's table words, the kinds and the camera's words |
| `kernels/mover_a/` | mover A: the directories (`directories.hpp`), the table page with the camera and SHADE's table (`table.hpp`), an item's planes and word (`items.hpp`), the command (`light.hpp`): the pack CPU's asks served first |
| `kernels/mover_b/` | mover B: the colour planes back to the frame (a band: its rows) and the profile page (`light.hpp`), its timed waits (`sends.hpp`); shown (`shows.hpp`, built with `PRISM_LIGHT_SHOWS`): the thresholds, an item converted by the display stage's writer and written to its display page, mover B's profile words |
| `kernels/unpack.hpp` | the unpack CPU: the pack CPU's mails served (a buffer's front page, a pop) |
| `kernels/pack/dst.hpp` | Dst for a quarter tile, the numbers the row's steps share |
| `kernels/pack/floats.hpp` | a float's bits and back, rsqrt on the vector unit |
| `kernels/pack/keys.hpp` | a row's point and texel keys: the shadow's taps, the background's, the glass's mirrored view |
| `kernels/pack/row.hpp` | a row's colour: sun, lamps, specular, sky, ambient, emissive, background |
| `kernels/pack/field.hpp` | the indirect field: the cell, the corners' keys, the weights, an axis's blend, I |
| `kernels/pack/tone.hpp` | the command's numbers, the tone step, graded rows, the glass's C toned |
| `kernels/pack/glass.hpp` | the glass form: where the glass is in front, its weighted albedo and tau C |
| `kernels/pack/passes.hpp` | the command's state, the taps' and the field's scans and gathers in page passes |
| `kernels/pack/quarter.hpp` | a quarter tile: its planes in, its colour by form and terms, its planes out |
| `kernels/pack/light.hpp` | the command: items, quarters, the out pages, the counts and the profile page |
| `kernels/waits.hpp` | the compute threads' waits (`compute_mail`): LIGHT's give-up places, the wait's code and limit |
| `kernels/from_raster.hpp` | every include of the raster stage's kernels: its layouts, and on the pack CPU recip, order and float_bits |

What LIGHT shares with SHADE comes from `core/include`: the surface's words (`surface.h`), the texel pages (`texel_pages/`: the protocol, mover A's asks, the pages and their passes), the compute threads' mails (`compute_mail.hpp`) and the vector unit's calls (`sfpu.hpp`).

## The class

Every buffer is an own field with its real pages (raw where a page is not a 32 x 32
tile): the two directory pages, the items' words, the planes ring (20 pages: an item's
15, or 20 in the glass form, pushed five at a time), the table page (LIGHT's table, the
camera, SHADE's table after it), the asks and answers of the light pages, the out
pages, and its parts of the command space (layout `texel`, with SHADE): the 129 slots,
the pack thread's work (the texel indices, then the profile's counters) and the page
passes' hash (`texel_work`). The fields it shares (`in_planes`, `frame_table`,
`texel_asks`, `texel_dones`, `command_space`, `out_ring`) are each defined once in
`prism.core.fields`, sized by the largest need its users register (this class's in
`device.py`). The table page's need is LIGHT's 1,024 words and SHADE's table through its
last material row (what the glass form reads), from the scene's numbers in the load's
capacity, stepped as SHADE's and never fewer than its least (32 KB); its words reach the
kernels as `PRISM_FRAME_TABLE_WORDS`, and `kLightShadeTableBytes` is the field's bytes
after LIGHT's table (`docs/internals/material/texture_model.md`). The command space is the space a handler has for the length of its
command: each stage lays its parts in it from byte 0, the stages' layouts overlapping,
its size the largest stage's; nothing in a part outlives the command. A part's address
is the space's base and the part's byte (`core/include/texel_pages/space.hpp`, the
bytes as the build's defines). The kernels name
the fields by the class header's names (`kFieldInPlanes`, ...); nothing is kept in L1
between commands.

The command's words: the frame's directory, the table's address in the regions' bank (0:
the surface's table tensor), SHADE's table (glass), the camera's address, the glass
layer's directory, the surface's directory (the glass layer's in the glass form), the
bank and the grid (grid.h's a8), the form (`kLightLinear`, `kLightGlass`, else
displayed; `kLightShown` with the displayed or the glass form).

## Shown (the option `light_shows`)

The presets `lit_tile` and `gi_tile` are `lit` and `gi` with the build option
`light_shows` (False by default), resolved when the program is made: the kernels' define
`PRISM_LIGHT_SHOWS`, the units' `DIRECT_LIGHT_SHOWN` and `POST_SHOW_BY_LIGHT`. The last
LIGHT command of a colour view carries `kLightShown`; the pack CPU and mover A see the
form without it. In place of writing an item's three colour planes to the frame, mover
B converts them where they are in the out ring with the display stage's own functions
(`post/show/kernels/write.hpp`, `convert.hpp`: `colour_rows`, `thresholds_of`, the
writer's state) into one of two scratch pages and writes the item's rows to its tile's
page of the display (page `tile`, as SHOW's with `first` 0, `across` 32); a scratch
page is used again once its last write has left. The thresholds are read once a command
from the display stage's region `show_table` into the writer's directory page, so the
display's controls (transfer, gamma) work unchanged. The words it reads are in the
surface's directory page beside LIGHT's (`surface.h` `kSurfaceShowDisplay`,
`kSurfaceShowTable`, `kSurfaceShowPages`), written by the host at `bind` from the
display tensor (slot `display.picture`, given by the display stage's host with the
option) and the region's address in the loaded run. The scratch pages and buckets are
the own field `shown_scratch` (16,384 bytes) of `LightShown`, the class made in place
of `Light` with the option; `Light` is unchanged. Mover B's cycles converting and writing, its rows and items go to
LIGHT's profile page after the pack CPU's words (`kLightProfShow*`). The frame's colour
planes are not written in that command: nothing after it reads them.


## In the frame's thread

The preset `lit` (`configs/pipeline/lit.py`) runs raster, material.texture,
direct.shadow_pcf, direct.light and post.show, in that order. The sun's unit has no
frame work, but its slot is read by this one. Once a COLOUR view, after every layer's
SHADE, the unit reads its words. From the view's first layer row it takes the frame's
directory (slot `frame.visibility`) and LIGHT's table (slot `light.shadow_map`: the
sun region's column `sun_table`). The camera's address is the view's (`camera_at`), and
the bank and grid are `bank + 1 | grid`. Its numbers give the surface's directory: the
texture stage makes the surfaces (its option `lights`), this host writes LIGHT's words
into their directory pages. With
a glass layer (the number `light_glass`, 1 + its index) it runs the linear form, then
the glass form: the glass row's directory, SHADE's table (slot `mesh.attributes`, the
texture unit's column) and the glass surface.

## Checking

`python scripts/run/preset.py --pipeline lit --scene
<scene> --view overview --size 1024 1024` runs the preset's frames by the thread; the
records are in `measurements/lit_frame/`.
