# direct.shadow_pcf

The sun's shadow map drawn on the card by the frame's own units: the thread command
`sun` builds one DEPTH view a quadrant of the map (its camera, a quadrant's grid, its
pages of the map as the target) and runs each through the director (`dr_view`), as the
frame runs the eye's; `fit` draws a map fitted to a slice of the eye's view, `lamps`
the lamps' faces, the same way. Each unit decides for itself what a DEPTH view needs. It has no
class and no frame work; it writes `light.shadow_map` and gives its views as
`view.depth`. LIGHT filters the map with its taps (the PCF).

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | the declaration (`SHADOW_PCF`), registered as `direct.shadow_pcf` |
| `unit.py` | the thread unit: serves `sun`, `fit` and `lamps`; regions `sun` (from the host) and `sun_times`; the column `sun_table`, shared with slot `light.shadow_map`; gives `light.shadow_maps` |
| `thread/direct_shadow_pcf_unit.c`, `.h` | SUN: the sun region's words, a DEPTH view a quadrant, the whole map's coarse levels, the times row; FIT: a fitted map's DEPTH view and coarse levels, the half swapped in; LAMPS: lamp faces' DEPTH views and coarse levels; the region's, the page of maps', a record's and the times row's word places |
| `host.py` | `ShadowHost`: the lights at the sun (the map's side from the option `shadow_side`, else the lights'), the quadrants, the fitted maps and the lamps' faces (the views of its own), slot `view.depth` (their cameras), slot `light.lamp_faces` (each lamp's first face record and faces), the map's tensor (the light pages, else its own), the region's own words (from `SHADOW_PCF_SUN_AT`), the column naming LIGHT's table, the SUN command asked of the loop when the sun moves, FIT and LAMPS, the control `sun`, the maps read back, the times |
| `kernels/share.hpp` | a map's 2 x 2 taps on the pack CPU's vector unit (LIGHT includes it): `point_taps` from a point through one map's camera, `coordinate_taps` from map coordinates whose map's numbers (first page, pages across, width, height) are each lane's own or the same in every lane, `project` the coordinates of a point |
| `model/share.py` | the twin of `kernels/share.hpp` in numpy |
| `model/maps.py` | the page of maps as the header lays it out: its words, the two halves of records, a record's words; the levels' slots, tops and coarse pages; maps and levels read back |
| `model/faces.py` | `Faces`: the lamps' faces (the reference's `lamp_maps.lamp_faces`), their records, pages and slots, the LAMPS commands paced by the time a face takes |
| `model/fit.py` | `Fits`: the records of both halves, the fitted cameras kept while they hold the eye's slices (the reference's `kept_cameras`), the FIT commands of a redraw, the half the frames read |
| `model/region.py` | the sun region as the header lays it out: LIGHT's table, the sun's words and a camera a quadrant (the light model's `quadrant_cameras`); the lights at a sun; the times rows |
| `check/sun_map.py` | the sun set, frames, the card's map against the reference's at that sun (the light stage's `sun_check`), the passes and times |
| `check/lamp_maps.py` | frames until every lamp face is drawn, each face's map against the reference's (`lamp_maps.face_view`) and its levels, the LAMPS commands and the faces' times |

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

## The page of maps

Every map the lookup may read has a record in the page of maps: the sun's whole map
first, then each fitted map (the option `cascades`, 0 by default), then each lamp face
(the option `lamp_maps`, true by default).
The page sits in the region `sun` after the quadrants' cameras, at the byte the sun's
word `SHADOW_PCF_MAPS_AT` gives (the thread's image holds 16 regions, all taken, so the
page and the levels' work bytes are parts of the unit's one region, apart from LIGHT's
table). A record is `SHADOW_PCF_RECORD_WORDS` words: the map's camera as a block of the
director's camera words first, then its tensor, first page, pages a row, width, texel,
bias, filter, margin, levels, the slots' tensor and first slot, its kind, which
cascade (a face: its lamp times 256 plus the face of the lamp), the view that draws it,
the tops' tensor, the coarse levels' tensor and first page, its pages down, the grid
word and tiles of its view. The page holds the records twice. The frames read one
half, `1 + half` given as slot `light.shadow_maps`; a redraw writes the other.

## The lamps' faces

A lamp's faces are those of `prism_reference.direct.lamp_maps`: a cosine lobe (an
area light's stand-in) a hemicube (a front face of 512 and four halves of 512 x 288),
a point a cube of six faces of 512, a spot one map of 1,024 over its cone, each with a
guard band past its edges. A lamp does not move, so a face's record is the same in both
halves and its map has one place, in the unit's own maps' tensor after the fitted maps'
(with the levels, its coarse levels after theirs, its slots after theirs). Face `k` is
view `1 + quadrants + cascades + k`. The command `lamps` (words: the first face's record
and the faces) draws faces in turn, each its DEPTH view and its levels, into the half
the frames read. The host asks for one before the frames while a face is not drawn
(after `sun`, beside `fit`), one face the first time, then as many as half a second
holds at the time the last command took a face (the director gives up a wait after a
second); a reload draws them all again. A face's view costs what the scene's ranges
cost, not what its texels do. Slot `light.lamp_faces` gives each lamp's first face
record and its faces in `lamp_faces`' order ((0, 0) for a lamp without faces), so a
lookup goes from a lamp to its records. A face's record leaves its texel and bias
words 0: the lookup's numbers for a lamp are its own host's.

## The taps

`kernels/share.hpp` turns a point into a map's 2 x 2 taps: the point moved one texel
along its normal, projected by the map's camera (1/z kept), the coordinates less a
half and floored, each tap's key `(first + page) << 10 | texel` (0 outside the map) and
the bilinear fractions. `point_taps` takes one map's numbers for every lane (the sun:
LIGHT's keys); `coordinate_taps` starts from coordinates a caller has already, and
takes the map's first page, pages across, width and height either as numbers for
every lane (`Bits`) or as Dst vectors of each lane's own (`Lanes`), so lanes that chose
different faces look up their own maps in one pass.

## The fit kept beside the frames

A fitted map covers one slice of the eye's view (the reference's practical split of the
option `cascade_reach`, else the scene box along the view) widened on each side by the
option `cascade_margin` (a share of the slice, 0.25 by default), its half width on steps
of 2^(1/8) and its centre on its own texel grid, so a fit made again nearby draws the
same texels. Each frame the host tests the fits against the eye's slices (`fit_holds`):
a still camera costs nothing. When one no longer holds, the host fits it again, writes
the half the frames do not read (a refitted map at its other pages, a kept one at the
same) and asks one `fit` command a refitted map. The loop sends one between two frames;
each draws its map's DEPTH view (view `1 + quadrants + cascade`) and its levels, and the
last one swaps the half in. The frames meanwhile read the old half: a point outside the
old fits takes a coarser map, never a wrong one. When the sun moves, the host writes the
other half with the whole map at the new sun and no fitted map, and `sun` swaps it in
with the new map; the fits are then drawn again one by one.

A fit's view adds to one frame's gap what its frustum takes of the scene: on
italian_flat a fitted view's frustum holds 16 % (the near map) and 80 % (the far map) of
the scene's triangle blocks, on lynxsdesign 38 % and 43 %. The margin trades redraws for
edge error: with the reach of the scene box, 0.25 costs an edge error of 0.117 on sponza
(0.111 at 0.1), 0.162 on italian_flat close and 0.105 at its camera (0.163, 0.101 at
0.1), against about a second of walk between redraws.

## The levels

With the option `shadow_levels`, each map has its levels: level `l + 1`'s texel is the
largest 1/z of level `l`'s 2 x 2 (each side halved, rounded up; a texel past the edge
empty), down to 1 x 1 (no 1/z is negative, so the reduction
compares bits). A level is a reduction of pages a core already holds when it writes them,
so the tile thread makes the levels finer than a tile: the DEPTH view's depth step
(`raster/steps/depth`, `depth_out`), on the data-movement CPU that turns a tile's block
row-major, reduces the block to its 16 x 16 and writes them to the tile's slot (a 2,048 B
page of the slots' tensor, `thread/depth_levels.h`). A whole tile also reduces down to
1 x 1 and writes its 1,376 B of levels and a 64 B top (its 1 x 1 and a mark that the slot
is whole); a band writes only its rows of the 16 x 16. The DEPTH view gives the step the
slots' tensor, the shift from a page of the map to its slot and the tops' tensor
(`dr_view_t`; none: no levels).

The levels coarser than a tile are a reduction of one texel a tile, small enough for the
X280: before a map's views the unit zeroes its tops, after them it fetches the tops (a
2,048 map: 64 x 64 of them), ends each tile whose top is not marked (drawn in bands: its
slot fetched, reduced from its 16 x 16, stored), reduces the tops' grid level by level and
stores each coarse level as a page of the fitted tensor. `sun` does it for the whole map
around its quadrants (sent at every load), `fit` for a fitted
map around its view. The record names the slots' tensor and first slot, the tops' tensor,
and the coarse levels' tensor and first page.

Only a tile thread whose DEPTH step has the word `levels` writes the slots and tops (the
threads' presets `lit_threads`, `gi_threads`); the stage-wise presets draw a DEPTH view
with no depth step. There the X280 would read slots nobody wrote, end every tile as a band
(a 1,024 map's 1,024 tiles, a 2,048 map's 4,096) and store levels of nothing, so the host
makes none: with `shadow_levels` asked on such a preset the maps have no levels, the
records say so (`LEVELS` 0) and `levels_state()` gives "not made"
(`prism.program.threads.tile_option.depth_levels` decides from the option `tile_thread`).

## The views' capacity

Capacity belongs to a view kind and a layer. The host gives the quadrants', the fitted
maps' and the faces' cameras and a quadrant's frame size (no fitted map or face is
larger) as slot `view.depth`. The raster host makes the
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
same at load. The card draws the map at every load: a map baked into the scene's
lighting file is never what the frames read, so a file baked by older code (or by the
host's reference raster) cannot put its faults on the card, and the card's map is
always the one its own raster draws.
The host then asks for `sun` (`commands()`): the loop sends it after the hosts' views
and before the next FRAME, as a times row of its own (`Loaded.serve(row=True)`), and a
code takes the frame's recovery: the row names the view and the layer, the raster host
grows that view kind's capacity for that layer, one reload, and `sun` is sent again
(`served()` keeps it asked until a 0). Below the horizon nothing is sent. On the card,
`sun` calls `dr_ready` (the numbers, and the units' setup once) before its rows are
started, so neither row times the setup, then runs each quadrant's view; it writes a director row (`dr_row_start`, `dr_row_end`: the units'
parts summed over the quadrants, the code, the view and layer that gave it) and a row
of its own region `sun_times`: the number, the code, the pass's ticks, the map, the
levels' ticks, their copies', the tiles ended on the X280, the command and each view's
(a quadrant's, a fitted map's, a face's).

## Checks

`python -m checks.shadow_maps` walks at the viewer's speed with fitted maps on and
compares every map the frames read with the reference's at its camera, and every map's
levels with the reference's levels of the card's map (exact).

`check/lamp_maps.py` (`--check prism.stages.direct.shadow_pcf.check.lamp_maps.check`
of `scripts/run/preset.py`, on a scene with the file's lamps) does the same for each
lamp face and its levels.

`python -m checks.shadow_share` (no card) checks `model/share.py`: the sun's keys
against the reference's taps (`prism_reference.direct.access`) key for key, and keys
from each lane's own map against each map's alone.

`check/sun_map.py` compares the card's map with the reference's: texels apart by more
than 1e-5, and texels empty on one side only, by the reference's layer and by quadrant.
The preset `lit` reports it when a pass ran (the light stage's `check/thread_frame.py`).
