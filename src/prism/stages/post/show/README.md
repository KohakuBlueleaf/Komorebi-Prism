# post.show

The frame converted for display on the card: SHOW turns the frame's colour planes (the
raster stage's `frame.visibility`) into 8-bit pixels, a page of the display tensor a
tile, and the thread's PUSH puts the frame's pages in host memory, where the host untiles
them into the picture. It fills the item `post` and writes `display.picture`.

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | the declaration (`SHOW`), registered as `post.show` |
| `device.py` | `Show`, the class on the card: `show` (the colour as R, G, B, 255, the thresholds in its field `thresholds`) and `copy` (plane 0 word for word into pages of another tensor); the frame program's compute set |
| `entries.py` | the tables it reads: the raster stage's directory page (`DirHead`, `DirFrames`, `DirItem`), imported |
| `host.py` | `ShowHost`: the capacity, the display and profile tensors, the thresholds' table, the push armed for a frame's grid, the picture (pushed, or read back) |
| `unit.py` | the thread unit (the frame role): takes `frame.visibility` (the columns the raster unit shares), its regions `show_table` and `show_push`, its numbers and times |
| `thread/post_show_unit.c`, `.h` | a COLOUR view's SHOW, then the PUSH from the host's words, the frame's key in the nonce word; a DEPTH view's COPY of its 1/z into the view's target (no PUSH) |
| `check.py` | the displayed picture (pushed and read back) against the host's conversion of the frame and against the reference of the stage before it; the times' medians |
| `model/table.py` | the thresholds' table, the writer's conversion on the host, its check against `to_srgb8` |
| `model/pages.py` | the display's pages untiled, the pages a frame pushes, COPY's pages |
| `kernels/show.h` | the layouts: the planes an item, the table, the buckets, the scratch pages, the profile |
| `kernels/space.hpp` | the stage's part of the command space: the scratch pages' address |
| `kernels/convert.hpp` | the conversion: thresholds, buckets, a tile's rows to pixels |
| `kernels/read.hpp` | mover A: an item's planes into the planes buffer |
| `kernels/write.hpp` | mover B: an item converted (or copied) and its rows written |
| `kernels/profile.hpp` | mover B: the profile page |

## A command

Each core walks its directory page (the raster stage's FILL wrote it): mover A reads an
item's three colour planes (a band: its rows) into `item_planes`, two items deep; mover
B converts them through the thresholds' buckets into one of two scratch pages (the
stage's part of the common field `command_space`, `prism.core.fields`, its address from
`kernels/space.hpp`; it lives within the command) and writes
the item's rows to its tile's page of the display. The thresholds are the region
`show_table`, filled into a field at each command. `copy` reads plane 0 and writes it
row-major to page `first + (tile / 32) across + tile mod 32`.

## The display's transfer

The host's controls are the transfer (power, the default, or the standard piecewise
sRGB) and the power's gamma, from 1.0 to the most the writer's buckets hold
(`model.table.most_gamma`, computed from `kShowBucketBase`); the default is 2.2. A
change makes the thresholds' table again and writes it into `show_table` of the live
run; the next frame's SHOW reads it. At each command the writer fills the buckets from
the first threshold's up to 1.0 (a lower first threshold fills more), and a value
under the first threshold is 0 without its bucket being read.

## Checks

`scripts/run/preset.py --pipeline raster` or `textured` (the preset's displayed picture
against the host's conversion and the reference).
