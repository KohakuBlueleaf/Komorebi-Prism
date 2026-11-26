# Raster: the card's data on the host

`prism.stages.raster.model` holds, in numpy, what the raster stage's card program reads
and writes: the triangle records, the list pages and the directory, the counters COUNT
leaves, the bands of heavy tiles, the middle pass between COUNT and SETUP, and the frame's
pages. `prism.core.capacity` and `prism.stages.raster.capacity` give the sizes a load is
built for. The thread's middle pass is plain C in `stages/raster/thread/`
(`raster_middle.c` the parts the thread calls, `raster_middle_whole.c` the whole step in
turn); `python -m checks.raster_model` runs it on the host against `model.middle`.

The layouts come from the kernel headers (`kernels/raster.h`, `setup.h`), the frame's grid
header shared by every stage (`prism/core/include/grid.h`) and the thread's header
(`thread/raster_middle.h`). `prism.core.headers` reads their numbers
(`constexpr uint32_t` constants and `#define`s), and `model.numbers` is the one place the
model takes them from, so the host and the card cannot disagree on a word.

## The 32-word record

Every triangle record of the reference's setup becomes one 128-byte slot of 32 words
(`records.pack_records`): the three edge functions' `a`, `b`, `c` (words 0 to 8), the
edge thresholds (9 to 11), the `1/z` plane (12 to 14), the three colour planes (15 to 23),
the pixel box (24 to 27), the triangle number (28) and the record number (29); floats are
their float32 bit patterns.

- **Thresholds.** The fill tests a pixel inside an edge when `e > T`, comparing bit
  patterns in their total order (`-0 < +0`). An ordinary edge takes `T = +0` (0); a top
  or left edge, where `e == 0` is inside, takes the lower neighbour of `-0`,
  `0x80000001`, so that both `+0` and `-0` pass.
- **The box.** Its first column and its last column plus one are float16 bit patterns
  (exact for integers below 2,048), which the fill pushes as one-load immediates; the
  first and last rows are integers. A wide build holds the columns as float32.
- **The triangle number** is a float, as the fifth plane of the frame stores it.

## The mesh as blocks

COUNT and SETUP read the mesh de-indexed, 32 triangles a block (`records.mesh_blocks`):
18 vectors of 32 lanes, the x, y, z of corners 0, 1, 2 then their red, green, blue, laid
out in the order of the destination register's window (`window_words`: two slots share
each 64 words, a lane every second word), so the unpacker copies a block in as it is.
The last block is padded with triangles whose corners are all zero: zero area, culled.

## The camera area

COUNT and SETUP find their blocks in a camera area of the thread's regions
(`host.camera_area`; `setup.h`'s `kArea*`), the areas one after another, `kAreaPages`
(249) pages of 4,096 bytes each. Page 0 is the view's page: the camera's 16 numbers at
word 0 and the view's words at `kViewAt` (the grid word at `kViewGrid`, `grid.h`'s a8
bits). Pages 1 to 248 are one a core: words 0 and 1 the core's block range (first, end),
and at byte `kAreaCostsAt` (64) the 128 bytes of costs COUNT writes back. A command names
the area by its first page, so each core's range and costs are a whole page of their own.
There is an area a (view, layer), `view * layers + layer`; the layers are the most a host
of the pipeline holds (the raster host's opaque, masked and glass when it is given the
materials), so the region grows with them.

## The lists and their slots

A core's list is a stream of slots, 16 to a 2,048-byte page: for each item it fills, a
header slot (word 0 `kMarkTile`, then the tile, the number of records that follow, the
item's first row and end row), the records that reach the item in triangle order, the
next header, and at the end an end slot (word 0 `kMarkEnd`). The stream is padded to a
whole page. An empty item has no header: the fill's writer stores the empty planes
itself. Lists of all cores lie one after another (`lists.build_lists`).

An item is a whole tile, or a band: the rows `[first_row, end_row)` of a tile, both even.
A band's header and its id carry its rows; for a whole tile they are 0 and 32.

## The directory page

One 4,096-byte page a core: word 0 the core's first list page, word 1 its pages, word 2
its items, then from word 3 the item ids, at most 997 (`kDirMaxItems`). An id is the tile
in bits 0 to 15, for a band its first row in bits 16 to 21 and its end row in bits 22 to
27, and the top bit `kItemEmpty` for an item without records. Word 1,000 holds the pages
of each frame tensor and the words after it the tensors' addresses, at most 15.

## The cost model

The estimated cycles of a tile (`cost.tile_cost` from the lists, `cost.cost_of` from
COUNT's counters): 260 per (triangle, tile) entry, 60 per row a triangle covers inside the
tile, 6,800 per tile with triangles (its initialisation and read-out), and 2,000 for an
empty tile (the writer alone). They are fits to the fill's measured cycles; the thread's
header holds the same four numbers (`RM_COST_*`), and the model reads them from there.

Items go to cores balanced by cost (`cost.assign`): largest first, each to the least
loaded core, ties to the lower core; a round-robin assignment is kept for comparison.

## Heavy tiles and bands

When one tile's cost is above a core's mean load (the total over the fill cores), every
tile above `SPLIT` (0.33) of that mean is cut into `ceil(cost / (SPLIT x mean))` bands,
at most 16 (`bands.heavy_tiles`). Below that no tile is cut: splitting a scene whose load
is already even made the estimate worse.

The cuts come from COUNT's histograms: per tile, how many entries start and how many end
in each of the 16 two-row groups. Summed over the cores, the entries covering a group are
the starts so far less the ends before it (`cover_of`). A group's weight is `2 x 60 x
cover + 260 x starts`; the band bounds are where the running weight first reaches
`j / bands` of the whole, compared in integers as `bands x running >= j x total`
(`cuts`). A band's entries are those starting before its end row less those ending
before its first row (`band_count`), and its cost is that of a tile with those entries
and twice the covers of its groups as rows (`items_of`).

A band is an ordinary item: every pixel still sees the same triangles in the same order,
so the frame stays exact. A triangle that reaches two bands is set up twice.

## The middle pass

Between COUNT and SETUP, on the X280 thread (`model.middle.middle` is its host form):

1. **Totals.** Each tile's entries and rows summed over the counting cores, and its cost.
2. **Pick.** The heavy tiles and their band counts, as above.
3. **Cut.** For the heavy tiles, the histograms summed over the cores, the bounds, and
   the items in tile order: a tile whole, or its bands, each with its entries and cost.
4. **Sort.** The items by falling cost, stably (equal costs keep tile order).
5. **Assign.** Each item in that order to the least loaded fill core, from a heap of
   `load << 8 | core` (ties to the lower core). A core whose directory page is full takes
   no more items.
6. **Layout.** Each core's items in tile order; their headers' slots, one after another
   from the core's first page; the end slot; the pages it takes. SETUP's next slot for
   a (counting core, item) is the item's header slot plus one plus the item's entries in
   the counting cores before it.
7. **Compact.** On the card the thread does not write the directory and headers itself:
   it writes two words an item (owner and entries; header slot) and four a core (first
   page, pages, items, end slot), from which PLACE writes the directory pages, the headers
   and the end slots. Each item also gets a base word: its first record's slot, and 1 plus
   its tile's index among the heavy tiles in the top 9 bits (0 for a whole tile), from
   which SETUP's reader makes its next slots with the prefixes SUM and HSUM computed.
8. **Pages.** SETUP's items page (`item_table`): per tile its first item and their number
   (`first | count << 16`), then per item its rows (`first_row | end_row << 8`, 16 bits).

The C does the same in parts the thread spreads over its four cores: `rm_costs`
(totals), `rm_pick`, `rm_items` (cut), `rm_sort` and `rm_merge`, `rm_owners`,
`rm_compact`, `rm_base`. Its arrays are laid one after another for the frame's tiles
(`rm_lay`), so a frame's walks over them do not depend on the capacity. `rm_heavy` and
`rm_middle` run the whole step in turn, for the host check.

## The frame's pages

The fill writes, per tile, five 4,096-byte planes: depth (`1/z`, 0 where empty), red,
green, blue, and the triangle number (-1 where empty). A plane is in the order the
destination register's window is read out: pixel (row, column) is word
`64 (row / 2) + 16 (column / 8) + 2 (column mod 8) + row mod 2` (`frame.window_index`), so
two rows of a plane are 256 contiguous bytes, which lets a band write only its rows.
`decode_frame` and `frame_of` turn pages into images and back.

## The capacity

Every per-tile table, tensor and thread region is sized from a capacity in tiles that the
load chooses (`prism.core.capacity`): the most tiles of the frame sizes it renders
(lit: at least the sun's 32 x 32 quadrant), rounded up to 32 tiles (`need`), then to the
next step of 1,024 tiles times 1, 1.5, 2, 3, 4, 6, 8, 12, 16, ... (`step_of`), so that a
new frame size rarely builds the program again. A capacity never shrinks while a loop
lives (`at_least`). Grids up to 64 by 32 tiles use the narrow box words (6-bit tile
columns, 10-bit rows, float16 box columns); a wider grid loads wide. A frame's own loops
run over its tiles, not the capacity.

The heavy tiles' tables and the bands' items follow the load's fill cores, not the tiles
(`heavy_capacity`): a frame has fewer than `cores / SPLIT` heavy tiles and band items, so
the tables hold `cores / SPLIT + 1` heavy tiles (at most the tiles) and that many band
items rounded up to 32. Without fill cores (the host-stepped passes) they hold 256 and
1,024. The base word's 9-bit heavy index holds 510, so a load past 168 fill cores is
refused with the numbers. `capacity_defines` gives the kernels' build defines;
`numbers.sizes` the sizes `setup.h` computes from them. A frame's pages go to tensors of
510 pages (a whole number of 3- and 5-page items, about 2 MB), more when 15 tensors would
not hold them (`chunk_pages`).

## The lists' slots a load holds

Each layer's lists are sized when the host prepares (`RasterHost.guessed_slots`): the
entries its triangles give the view's tiles, a heavy tile's entries again in each further
band, a header an item and an end slot and a page's padding a core, in whole pages (times
the layer's `list_fraction`); the DEPTH views' lists by the most any of their cameras
needs. The entries come from the pieces' pixel boxes alone, not from the whole setup:
`setup.boxes` takes the positions' part of `corners` (`screen_pieces`: camera space, the
near plane's pieces, the screen coordinates, each piece's triangle) and the same steps
`setup` takes to its boxes, and `fill.tile_counts` counts a tile's entries by a
two-dimensional difference array (four corner adds a box, two running sums), the counts
`bin_triangles` gives without its per-entry arrays. The counts are made once
(`counts.kept_counts`) for a scene's positions, indices and camera, its frame's size and
the grid: kept in the process and under `$PRISM_CACHE/counts/` as one `.npy` named by the
first 16 hex digits of the BLAKE2b digest of those and a version number, the whole digest
in a `.json` beside it, compared on load (each written to a temporary name, then renamed).
A frame that needs more slots stops
with `RASTER_LISTS_SMALL` and the loop reloads with a quarter more.

A shaded frame's layers (opaque, masked, glass) and their mesh blocks come from the
texture model's `blocks.layer_blocks`, the same call the texture host takes its shade
blocks from: made once for a scene, its materials and the lit flag, kept in the process
and under `$PRISM_CACHE/blocks/` ([the environment](../../guides/environment.md)), read
back with a memory map by a later load of the same arrays.
