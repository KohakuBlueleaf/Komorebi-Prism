# direct.shadow_pcf

The sun's shadow map drawn on the card by the frame's own units: the thread command
`sun` builds one DEPTH view a quadrant of the map (its camera, a quadrant's grid, its
pages of the map as the target) and runs each through the director (`dr_view`), as the
frame runs the eye's. Each unit decides for itself what a DEPTH view needs. It has no
class and no frame work; it writes `light.shadow_map` and gives its views as
`view.depth`. LIGHT filters the map with its taps (the PCF).

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | the declaration (`SHADOW_PCF`), registered as `direct.shadow_pcf` |
| `unit.py` | the thread unit: serves `sun`; regions `sun` (from the host) and `sun_times`; the column `sun_table`, shared with slot `light.shadow_map` |
| `thread/direct_shadow_pcf_unit.c`, `.h` | SUN: the sun region's words, a DEPTH view a quadrant, the times row; the region's and the times row's word places |
| `host.py` | `ShadowHost`: the lights at the sun (the map's side from the option `shadow_side`, else the lights'), the quadrants (the views of its own), slot `view.depth` (their cameras), the map's tensor (the light pages, else its own), the region's own words (from `SHADOW_PCF_SUN_AT`), the column naming LIGHT's table, the SUN command asked of the loop when the sun moves, the control `sun`, the map read back, the times |
| `model/region.py` | the sun region as the header lays it out: LIGHT's table, the sun's words and a camera a quadrant (the light model's `quadrant_cameras`); the lights at a sun; the times rows |
| `check/sun_map.py` | the sun set, frames, the card's map against the reference's at that sun (the light stage's `sun_check`), the passes and times |

## The sun region

The region `sun` starts with LIGHT's table, at byte 0. LIGHT reads it from there: its
address is the column `sun_table` of every layer row, which the light unit takes. After
the table, on a line (`SHADOW_PCF_SUN_AT`), come the sun's words: the quadrants, the
quadrants in a row, a quadrant's grid word, its tiles, its tiles in a row and its rows
of tiles, the map's tensor, its first page and its pages. Each quadrant's camera
follows from `SHADOW_PCF_CAMERAS`, as many words as the director's camera. The sizes
follow the host's map: a side of `n` quadrants gives `n * n` views. Quadrant `q` is
view `1 + q`, and its pages start at `first + (q / n) TY (n TX) + (q mod n) TX`. The
side is the option `shadow_side` (whole quadrants of 1,024) or the lights' own map's.

## The views' capacity

Capacity belongs to a view kind and a layer. The host gives the quadrants' cameras and
a quadrant's frame size as slot `view.depth`. The raster host makes the
opaque and masked layers' own lists and directory for the DEPTH views, sized by its list
guess over those cameras at the quadrant's size and tiles (the most any quadrant needs),
and writes them into views `1 .. n`'s layer rows. The eye's size never changes them.

The region has two parts, each with one writer. The shadow host writes its own part
(from `SHADOW_PCF_SUN_AT`: the sun's words and the cameras) at load and when the sun
moves; LIGHT's table is the light host's alone, written once loaded and again whenever
anything in it changes (the sun, the tone, the terms, the field's scale). Both take the
sun from the run's options, which keep it across reloads.

## The command

`set("sun", (azimuth, elevation))` moves the lights' sun (the light stage's
`sun_lights`) and rewrites its part of the region; a sun given in the options does the
same at load.
The host then asks for `sun` (`commands()`): the loop sends it after the hosts' views
and before the next FRAME, as a times row of its own (`Loaded.serve(row=True)`), and a
code takes the frame's recovery: the row names the view and the layer, the raster host
grows that view kind's capacity for that layer, one reload, and `sun` is sent again
(`served()` keeps it asked until a 0). Below the horizon nothing is sent. On the card,
`sun` calls `dr_ready` (the numbers, and the units' setup once) before its rows are
started, so neither row times the setup, then runs each quadrant's view; it writes a director row (`dr_row_start`, `dr_row_end`: the units'
parts summed over the quadrants, the code, the view and layer that gave it) and a row
of its own region `sun_times`: the number, the code, the pass's ticks and each
quadrant's.

## Checks

`check/sun_map.py` compares the card's map with the reference's: texels apart by more
than 1e-5, and texels empty on one side only, by the reference's layer and by quadrant.
The preset `lit` reports it when a pass ran (the light stage's `check/thread_frame.py`).
