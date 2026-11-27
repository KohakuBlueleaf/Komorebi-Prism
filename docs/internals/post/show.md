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
They are what Blender's OpenColorIO evaluates, read from one file per scene.
`scripts/blender/view.py` runs inside the Blender that writes the scene's sidecar (`export.py`
calls it for every scene). It takes that configuration's optimized processor from scene
linear through the display, view and look, and splits it at its last 3D table:

- **The body:** everything up to and including the last 3D table, baked into one cube of
  16-bit entries. The cube's axes are the log2 of the channels after the processor's own
  matrix, on the log2 range its first logarithm maps to [0, 1]. When the body is that
  domain and one table, the cube has the table's own lattice, and the bake reproduces the
  table: AgX 57^3, Filmic 33^3. Otherwise it has 65^3.
- **The tail:** the operations after it, which act on each channel alike and never fall:
  AgX's 2.4 power and sRGB encode, Filmic's scale and curve. They become the display's 255
  thresholds, the same table SHOW already reads, found by bisecting the tail as OpenColorIO
  evaluates it.

A view without a 3D table (Standard) is the thresholds alone. The file `<stem>.view.npz`
holds the matrix, the range, the cube, the thresholds and a note of its own check against
OpenColorIO on random colours. Blender's `scripts/blender/view.py sidecar` writes it
beside a sidecar from the sidecar's `render` and leaves the sidecar as it is; the file
is found by its name (or by `render.view_tables` when an export names it there). A
display setting is not part of what a scene's conversion makes, so giving a scene its
view keeps its key, its name, its far field and its compared truths
([glTF scenes](../../guides/gltf_scenes.md)).

`prism_reference.post.view` evaluates the form in float32, written op by op as the card
does it:

- the 3 x 3 product, left to right;
- the clamp to the range;
- log2 as the exponent plus a 1,025-entry table of log2(1 + m) at the mantissa's top 10
  bits, linear over the rest;
- the scale to cells;
- tetrahedral interpolation: the fractions sorted, the corners 000, a, a + b, 111, the
  weights 1 - a, a - b, b - c, c summed in that order over the entries, then x 1 / 65,535;
- a byte: the count of thresholds at or under the value.

`view_of(sidecar)` gives the form, or None with a notice when the sidecar names a
transform but the file is missing; the standard sRGB transfer is then used.

`checks.view_transform` compares the form with Blender's own 8-bit save and with
OpenColorIO's values:

- AgX, Filmic and Standard: within 1 on the test picture and on sponza and italian_flat.
- Filmic with High Contrast or Medium High Contrast: within 1 on the frames, 2 on 0.01 %
  of the test picture's channels (pure primaries past 16).
- AgX + Punchy is open: largest difference 8 to 12, 0.05 % to 0.9 % of channels over 1.
  Its look mixes the channels between two 3D tables of the body (OpenColorIO's grading
  operations), so sampling the body on a lattice cannot follow it.

## A file's view transform on the card

The scene's display is read from its file's sidecar whenever a preset loads its
lights (`prism_reference.post.view.with_view`): the exposure, 2 to the power of
`render.exposure` (stops), and the view when its tables are there. The host's transfer
`view` is the default when the scene's sidecar has tables (the
option `view` gives a sidecar or a `.view.npz` path; `False` gives none). The thresholds
are the file's. The cube becomes a tensor of 4 KiB pages (`kernels/view.h`), one per
brick of 8 x 8 x 8 nodes, with bricks stepping 7 cells so that neighbours share a node.
A cell's eight corners therefore always lie in one page. An entry is two words (red and
green, then blue, 16 bits each). AgX has 512 pages, Filmic 125, and a 65^3 cube 1,000.
The region `show_table` holds, after the thresholds' page, two pages of the words the
fetch needs: on, cells, bricks across, the pages' address, the range, the matrix and the
log2 table (1,025 entries; a value between two entries is interpolated linearly).

One function, `kernels/view_fetch.hpp`, runs the fetch on the pack CPU's vector unit in
both forms of the stage, so the two are byte-equal by construction:

- each pixel's cube page: the matrix, the clamp, log2 from the table, the cell and its
  brick (cell x 293 >> 11 is cell / 7, because the CPU has no vector divide);
- passes: the distinct pages of 16-pixel parts gathered into 16 slots, a new pass when
  a part would need more than 16, each pass's pages read in one ask;
- the tetrahedral sum by gathers from the slots, in the reference's order with no fused
  products.

The vectors are four registers wide (e32m2). At eight, the compiler spilled whole
register groups to a stack frame sized by the vector length, and the pack CPU's stack
(1.6 KB) overflowed.

**In a tile thread**, the post step keeps the view's words (8 KiB, copied by the step's
begin), the slots (64 KiB) and a word a pixel (4 KiB); `prism/core` assigns them from
the core's L1. The pack CPU writes the values into the output block in place of the
copied planes and asks for pages through the frame's page requests (`ask_begin`,
`ask_post`, `ask_wait`). Meanwhile the unpack CPU serves the pack CPU's mails, as it
does in the material step. The mover converts the block by the thresholds as before.
The keeps are what the frame program's merged class can spare. With 32 slots,
`gi_threads` needed 20 KiB more L1 than the core has. With 16 slots, its command space
grows from 899,392 B to 977,216 B.

**In SHOW's class**, a pack part runs the same function. Mover A hands the pack CPU each
item's id and the L1 address of its planes, then serves its asks (`texel_pages`' asks and
dones, the command space's slots) until the item's end. The pack CPU converts the planes
in place and pushes a token. Mover B waits for the token before it converts the item.
The first word handed says whether the view is on. With the view off, the pack CPU ends
at once.

`model/view.py` holds the pages and the card's addressing in numpy. It is bit-equal to
the reference and counts each tile's passes and pages. On the reference's 1,024 x 1,024
frames with 16 slots, against SHOW's counts on the card (its profile; an item is a tile
or a band of one, so italian_flat has more items than tiles):

| frame | model: tiles, passes, pages | card: items, passes, pages | slots for one pass |
| --- | --- | --- | --- |
| sponza, AgX | 1,024, 1,025, 6,766 | 1,024, 1,026, 6,771 | 18 |
| italian_flat, AgX | 1,024, 1,024, 3,445 | 1,189, 1,189, 3,642 | 11 |
| italian_flat, Filmic High Contrast | 1,024, 1,026, 3,978 | 1,189, 1,191, 4,236 | 18 |

## The check

`check.py` compares, in the frames it checks, the pushed picture and the display read back
with the frame's colour read back and converted on the host (bit for bit), and with the
reference of the stage before it: the vertex-colour frame by `to_srgb8` after the raster
stage, `expect.check`'s report on the shaded frame after the texture stage.
