/* A tile thread's record and a slice of tiles: written by the sums on the cores, read
 * by the core that takes the thread and by the frame's thread. */
#pragma once

#include <stdint.h>

#define TR_LAYERS 4u /* the layers a record holds at most */

/* An item is a tile, or a band of the rows of a tile whose weight over every layer
 * passes the frame's TF_HEAVY; items are shared by all layers. A slice's records are
 * in order of weight (then tile, then first row), and its lists lie in that order from
 * the slice's place; inside an item's list the cores' entries follow each other by
 * rank, a core's own in the order of its ranges. A list holds records only.
 *
 * A record: TR_WORDS words.
 * word 0: tile | first_row << 16 | end_row << 24 (a whole tile: rows 0 to 32)
 * word 1: its weight (its entries over every layer)
 * word 2: the layers it has (a bit a layer)
 * word 3: the page its rows are written to (the display's, or a DEPTH view's target's)
 * words 4 + 2 l, 5 + 2 l: layer l's first list slot, from its slice's place, and its
 *   entries */
#define TR_WORDS 16u
#define TR_TILE(word0) ((word0) & 0xFFFFu)
#define TR_FIRST_ROW(word0) (((word0) >> 16) & 0xFFu)
#define TR_END_ROW(word0) ((word0) >> 24)
#define TR_LAYER_SLOT(layer) (4u + 2u * (layer))
#define TR_LAYER_ENTRIES(layer) (5u + 2u * (layer))

/* A tile thread's number in the tile pull: slice * TR_SLICE_RECORDS + its place in the
 * slice's records (in order of weight). TR_SLICE_RECORDS is the capacity's (a build
 * define): the records a slice holds at most. */
#define TR_NUMBER(slice, place) ((slice) * TR_SLICE_RECORDS + (place))
#define TR_SLICE_OF(number) ((number) / TR_SLICE_RECORDS)
#define TR_PLACE_OF(number) ((number) % TR_SLICE_RECORDS)

/* A slice's words, TS_WORDS a slice: what its sum wrote for the frame's thread, then
 * what the frame's thread wrote back for the cores.
 * word 0: its records (its items: every tile's bands, an empty tile's one too)
 * word 1: its weight
 * words 2 + l: layer l's entries over the slice (written by the sum)
 * words 2 + TR_LAYERS + l: layer l's place: its first list slot (the frame's thread's
 *   running sum over the slices) */
#define TS_WORDS 16u
#define TS_RECORDS 0u
#define TS_WEIGHT 1u
#define TS_ENTRIES(layer) (2u + (layer))
#define TS_PLACE(layer) (2u + TR_LAYERS + (layer))
