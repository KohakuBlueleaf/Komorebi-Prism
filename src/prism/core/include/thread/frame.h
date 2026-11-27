/* The frame's page: the block of a view's commands (at most 1,024 bytes), the words
 * every thread of that view shares. Written by the frame's thread. Places in words. */
#pragma once

#include <stdint.h>

#include "record.h"

#define TF_VIEW 0u          /* the view's index | its kind << 8 (TV_*) */
#define TF_PULL 1u          /* the pull this command is (TP_*), 0 for the sums */
#define TF_GRID 2u          /* the view's grid word (the regions' bank + 1 beside it) */
#define TF_CAMERA 3u        /* the camera's 64 bytes: their address, on 64 bytes */
#define TF_LAYER_COUNT 4u   /* the layers */
#define TF_RECORDS 5u       /* the tile threads' records: their tensor's address */
#define TF_SLICES 6u        /* the slices' words: their address in the regions' bank */
#define TF_SLICE_COUNT 7u   /* the slices */
#define TF_SLICE_TILES 8u   /* the tiles a slice holds (its run along a row) */
#define TF_HEAVY 9u         /* the weight above which a tile is cut into bands */
#define TF_TARGET 10u       /* the display's (or a DEPTH view's target's) address */
#define TF_RANGE_BLOCKS 11u /* the triangle blocks a count range holds */
#define TF_PAGE_FIRST \
    12u /* a tile's page in the target: TF_PAGE_FIRST + (tile / across) */
#define TF_PAGE_ACROSS \
    13u                /*   * TF_PAGE_ACROSS + tile % across (the display: 0, across) */
#define TF_ACCOUNT 14u /* the account's pages (a page a core; 0: none) */
#define TF_ACCOUNT_RECORDS 15u /* the records a core's page holds */

/* A view's kind */
#define TV_COLOUR 0u
#define TV_DEPTH 1u

/* A layer's words, TF_LAYER_WORDS a layer from TF_LAYER_AT */
#define TF_LAYER_AT 16u
#define TF_LAYER_WORDS 8u
#define TF_L_MESH 0u        /* its triangle blocks' address */
#define TF_L_RANGE_FIRST 1u /* its first range in the count and place pulls */
#define TF_L_BLOCKS 2u      /* its blocks */
#define TF_L_SHADE 3u       /* its shade blocks' address (0: not shaded) */
#define TF_L_LISTS 4u       /* its lists' address */
#define TF_L_COUNTS 5u      /* its counts: a page a core, a word a tile (its entries) */
/* its row histograms: a page a core, 64 bytes a tile (16 counts of entries starting in
   a 2-row group, then 16 of entries ending in one, uint16) */
#define TF_L_ROWS 6u
/* each core's positions: a page a core. A word a tile of a slice (32 a slice): a whole
   tile's first position, from its slice's place, or 0x80000000 | bands << 24 | its
   first band entry; then 2 words a band entry (TR_SLICE_RECORDS a slice): rows first |
   end << 8, and its first position */
#define TF_L_POSITIONS 7u

/* A step's own words follow, one a name of its `words`, assigned by prism.core as the
 * defines PRISM_TF_<STEP>_<WORD> from TF_STEP_AT, filled a view by the step's function
 * on the frame's thread. */
#define TF_STEP_AT (TF_LAYER_AT + TR_LAYERS * TF_LAYER_WORDS)
#define TF_WORDS 256u
