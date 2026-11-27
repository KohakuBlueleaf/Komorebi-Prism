# post.show: the frame for display, its unit and its host

`prism.stages.post.show` converts the frame's colour planes (the raster stage's
`frame.visibility`) into 8-bit pixels on the card, a page of the display tensor a tile, and
has the thread push the frame's pages to the host. Its picture is the displayed one; the
loop takes it because it is the last implementation in the pipeline that gives a picture.

## The conversion

A pixel's channel is `to_srgb8` of its linear value (`prism_reference.post.display`). The
card does not evaluate the curve: the host gives 256 thresholds (`model.table.show_table`),
the float32 bit patterns at which the byte steps, and the writer finds a value's byte by
its bucket (the top bits of its pattern above `kShowBucketBase`, 2^-32) and a short walk
over the thresholds from that bucket's first; a value under the first threshold is 0. The
buckets are filled at each command from the first threshold's bucket up, so a table costs
the range it uses, and the host may write another transfer's table between frames (the
power transfer up to `model.table.most_gamma`, the standard sRGB). `model.table.show_bytes`
is the same walk in numpy, and `table_check` compares it with `to_srgb8` on both sides of
every threshold, the clamp's ends and random colours, with fresh buckets and with those a
wider table left.

## On the card

`device.Show` has two handlers on the movers, both walking the core's directory page as
FILL wrote it (the head, the frames' tensors, then the items):

- `show`: mover A reads an item's three colour planes (a band reads only its rows) into
  `item_planes`, two items deep; mover B converts them into one of two scratch pages and
  writes the item's rows to the display page of its tile. The thresholds are the region
  `show_table`, filled into the field `table` at the start of each command; the buckets
  are built from it once a command. The writer's profile page ends the command.
- `copy`: plane 0 of each item, word for word, row-major, to page
  `first + (tile / 32) across + tile mod 32` of another tensor.


## The unit

The unit (`unit.py`, `thread/post_show_unit.c`) has the frame role: once a view, after
every layer's work of the units before it (the raster stage's passes, SHADE for each layer
in `textured`), so it shows the colour the last of them left in the first layer's frame:

- It `takes` `frame.visibility`. The raster unit `shares` that slot's columns (the
  directory, the frame's pages, the frame's tensors), so the layout gives the show unit
  exactly those words of the layer row as `DR_POST_SHOW_TAKES_FRAME_VISIBILITY_<COLUMN>`;
  it reads the directory's address from the view's first layer's row.
- Its numbers are the display's and the profile's addresses and whether it pushes.
- It builds SHOW with its class's builder in the merged program,
  `DR_POST_SHOW_BUILD(show)`, and runs it on every core.
- With the push on, it then issues the PUSH whose command words the host wrote into the
  region `show_push`, the frame's key XORed into the nonce word. Its times are `show` and
  `push`.

## In a tile thread

The threads' form converts on the movers as the post step (`steps/step.py`,
[steps, kinds and the tile thread](../program/steps.md)): pack copies the band's rows of
the first layer's three colour planes, kept in the core's memory, into a block of the
output `display` (a 16-byte header, then 12,288 bytes); the mover that takes the block
converts it in place by this stage's rule (`post_convert`, `kernels/convert.hpp`) and
writes the rows to the tile's display page. The step's begin, on mover A once a command,
reads the thresholds from the region `show_table` (the step's word `table`) and makes the
kept thresholds and buckets. No SHOW or PUSH command is sent (`push` false in the
threads' presets); the host is `ShowThreadsHost`, which gives the display as slot
`display.picture` and reads its pages back for the picture. A DEPTH view's `depth_out`
step writes its 1/z plane row-major to the target the same way.

## The host

`ShowHost` holds the display tensor (a page a tile of the capacity, as the raster stage's
capacity), the profile tensor and the table. At a frame's view it writes the unit's
numbers once a loaded run, arms the push for the frame's grid (a channel transfer of the
display's first `TX * TY` pages, built again when the grid changes) and writes the frame's
key into the push words. Its picture waits for the pushed pages and untiles them, the
frame's size of them (H, W, 4); without the push it reads the display's pages back
instead. `display()` is that read-back, which the check compares as well. Being the last
host that gives pictures, it is the only one the loop asks (`Host.pictures`).

## A file's view transform (the reference)

Blender's view transforms (AgX, Filmic, their looks) are not a curve of their own here.
They are the operations Blender's OpenColorIO evaluates, read from the scene's files.
`scripts/blender/view.py` runs inside the Blender that wrote the scene's sidecar. It asks
that Blender's configuration for its optimized processor, from scene linear through the
display, view and look. It writes the processor's operations to `<stem>.view.npz` beside
the sidecar, and the sidecar names that file in `render.view_tables`; `export.py` does
this for every scene it writes. The operations are matrices, logarithms, powers, powers
with a linear segment, 1D tables and 3D tables. A look with an operation outside these
(AgX's looks use OpenColorIO's grading operations) is dropped, and the sidecar's
`render.view_notes` says so; a view with one is written as no tables.

`prism_reference.post.view` evaluates the operations in float32. Its 3D tables use
OpenColorIO's tetrahedral interpolation. `view_of(sidecar)` gives the operations, or None
with a notice when the sidecar names a transform but no tables are beside it; the
standard sRGB transfer is then used. `post.described.displayed` takes them as `view`.
The check `checks.view_transform` compares them with Blender's own 8-bit save and with
OpenColorIO's values (at most 1 apart in 8 bits).

AgX is a 57^3 table addressed in the log2 of E-Gamut. Its generator mixes 40 % of the
HSV hue between the inset and the outset, and adds guard rails, so no 3 x 3, 1D table,
3 x 3 form reproduces it. Filmic is a 33^3 desaturation table addressed in log2, followed
by a 4,096-entry curve. Its looks replace the curve: Blender applies the desaturation
twice, and the reference reproduces that because it follows the operations.

## The check

`check.py` compares, in the frames it checks, the pushed picture and the display read back
with the frame's colour read back and converted on the host (bit for bit), and with the
reference of the stage before it: the vertex-colour frame by `to_srgb8` after the raster
stage, `expect.check`'s report on the shaded frame after the texture stage.
