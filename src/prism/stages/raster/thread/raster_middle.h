/* The middle pass between COUNT and SETUP in plain C (X280 thread, host check): costs,
 * bands, items to cores, list layout and directory, next slots. */
#pragma once

#include <stdint.h>

/* RM_TILES, the tables' tiles: the frame's capacity the load chose, a build define; a
 * frame's grid has at most these. */
#ifndef RM_TILES
#error "RM_TILES: the frame's capacity in tiles, chosen at the load"
#endif
#define RM_GROUPS 16u /* 2-row groups of a tile */
#define RM_MAX_BANDS 16u
/* RM_MAX_HEAVY heavy tiles, RM_BAND_ITEMS bands' items: from the load's fill cores; a
 * frame has fewer than cores / RM_SPLIT of either. */
#if !defined(RM_MAX_HEAVY) || !defined(RM_BAND_ITEMS)
#error "RM_MAX_HEAVY, RM_BAND_ITEMS: from the load's fill cores"
#endif
#define RM_MAX_ITEMS (RM_TILES + RM_BAND_ITEMS)
/* a core's counters: entries per tile, then rows */
#define RM_COUNTERS (2 * RM_TILES)
#define RM_MAX_CORES 248u
#define RM_DIR_WORDS 1024u /* a directory page (raster.h) */
#define RM_DIR_FIRST 0u
#define RM_DIR_PAGES 1u
#define RM_DIR_ITEMS 2u
#define RM_DIR_IDS 3u
#define RM_DIR_MAX_ITEMS 997u
#define RM_ITEM_EMPTY 0x80000000u
#define RM_ITEM_ROW0_SHIFT 16u
#define RM_ITEM_ROW1_SHIFT 22u
#define RM_PAGE_SLOTS 16u
#define RM_MARK_TILE 0xFFFFFFFEu
#define RM_MARK_END 0xFFFFFFFFu
#define RM_BASE_SLOT_BITS 23u /* kernels/setup.h kBaseSlotBits */
#define RM_ITEM_WORDS 2u
#define RM_CORE_WORDS 4u

/* Cost model and the cut: per entry, per row, per tile with entries, per empty tile; a
 * tile above RM_SPLIT of a core's mean load is cut. */
#define RM_COST_TRI 260u
#define RM_COST_ROW 60u
#define RM_COST_TILE 6800u
#define RM_COST_EMPTY 2000u
#define RM_SPLIT 0.33

/* An item: a tile's rows [first_row, end_row) (0, 32: the whole tile), its entries. */
typedef struct {
    uint32_t tile, first_row, end_row, total;
} rm_item;

/* A list slot the middle pass writes: a header (RM_MARK_TILE, tile, records, rows) or a
 * core's end slot (RM_MARK_END). */
typedef struct {
    uint32_t slot, mark, tile, count, first_row, end_row;
} rm_mark;

/* Bytes rm_lay lays for `tiles`: 32 a tile, 44 an item, the cores' and heavy tiles'
 * arrays, 8 to spare an array (rm_lay names each). */
#define RM_LAID_BYTES(tiles)                                                          \
    (32u * (tiles) + 44u * ((tiles) + RM_BAND_ITEMS) + 4u + 28u * RM_MAX_CORES + 4u + \
     256u * RM_MAX_HEAVY + 8u * 18u)

/* The middle pass's arrays, laid one after another from `space` for the frame's tiles
 * (rm_lay): a frame's walks over them lie the same whatever the capacity. */
typedef struct {
    uint64_t *entries, *rows, *tile_cost; /* per tile; entries, rows over the cores */
    uint64_t* cost;                       /* per item */
    uint32_t *order, *spare_order, *owner, *header;
    uint64_t* load;       /* each fill core's cost, rm_owners */
    uint64_t* heap;       /* its heap of load << 8 | core */
    uint32_t* first_item; /* RM_MAX_CORES + 1: each core's items in spare_order */
    uint32_t* next_slot;  /* per item: next slots while they are written */
    uint64_t (*histograms)[2 * RM_GROUPS]; /* heavy tiles' counts over the cores */
    int32_t* heavy_of; /* per tile: index among the heavy tiles, or -1 */
    uint32_t *slot_counts, *item_counts; /* rm_compact's, per core */
    rm_item* items;                      /* per item */
    uint32_t* tile_item; /* tiles + 1: the items of a tile start at tile_item[tile] */
    uint32_t laid;       /* the tiles they are laid for */
    uint64_t space[(RM_LAID_BYTES(RM_TILES) + 7u) / 8u];
} rm_scratch;

/* The per-tile and per-item arrays laid from scratch->space for a frame of `tiles`
 * (at most RM_TILES): a frame's arrays follow its tiles, not the capacity. */
void rm_lay(rm_scratch* scratch, uint32_t tiles);

/* The middle pass in parts for the four cores, ranges side by side: rm_costs (tiles),
 * rm_pick, rm_clear (fill cores), rm_hist, rm_layout, rm_next (items). */

/* Entries, rows and cost of tiles [first_tile, end_tile) over the cores (a core's
 * counters: entries a tile, then rows from rows_at; RM_COUNTERS words a core). */
void rm_costs(
    const uint32_t* counters,
    uint32_t rows_at,
    uint32_t cores,
    rm_scratch* scratch,
    uint32_t first_tile,
    uint32_t end_tile
);

/* The tiles to cut among tiles [0, tiles) (the frame's grid), ascending, and their
 * bands: returns how many; the first RM_MAX_HEAVY of them are written. */
uint32_t rm_pick(
    rm_scratch* scratch,
    uint32_t fill_cores,
    uint32_t* heavy,
    uint32_t* bands,
    uint32_t tiles
);

/* Zeroes the directory pages of fill cores [first_core, end_core). */
void rm_clear(uint32_t* directory, uint32_t first_core, uint32_t end_core);

/* The heavy tiles' counts over the cores into scratch->histograms. */
void rm_hist(
    const uint16_t*
        histograms, /* (setup cores, heavy_count, 32): starts, then ends per group */
    uint32_t setup_cores,
    uint32_t heavy_count,
    rm_scratch* scratch
);

/* rm_layout in parts: the items of tiles [0, tiles) in tile order (0: too many), then
 * the items to cores in scratch->owner (0: no or too many cores). */
uint32_t rm_items(
    const uint32_t* heavy,
    const uint32_t* bands,
    uint32_t heavy_count,
    rm_scratch* scratch,
    rm_item* items,
    uint32_t* items_found,
    uint32_t* tile_item,
    uint32_t tiles
);
uint32_t rm_assign(uint32_t fill_cores, rm_scratch* scratch, uint32_t items_found);
/* rm_assign in parts: items [first, end) by falling cost (stable), two sorted
 * neighbours into one (the first's ties first), then each to the lightest core. */
void rm_sort(rm_scratch* scratch, uint32_t first, uint32_t end);
void rm_merge(rm_scratch* scratch, uint32_t first, uint32_t middle, uint32_t end);
uint32_t rm_owners(uint32_t fill_cores, rm_scratch* scratch, uint32_t items_found);

/* After rm_assign, PLACE's words: the lists' slots, or 0 when a core has more than
 * RM_DIR_MAX_ITEMS items. */
uint32_t rm_compact(
    uint32_t fill_cores,
    rm_scratch* scratch,
    const rm_item* items,
    uint32_t items_found,
    uint32_t* item_words, /* RM_ITEM_WORDS per item */
    uint32_t* core_words  /* RM_CORE_WORDS per fill core */
);

/* The lists' slots, or 0 when the counts do not fit (a core over RM_DIR_MAX_ITEMS
 * items, RM_MAX_ITEMS items, cores or heavy tiles); counts: scratch->histograms. */
uint32_t rm_layout(
    uint32_t fill_cores,
    const uint32_t* heavy,
    const uint32_t* bands,
    uint32_t heavy_count,
    rm_scratch* scratch,
    rm_item* items,
    uint32_t* items_found,
    uint32_t*
        tile_item, /* RM_TILES + 1: the items of a tile start at tile_item[tile] */
    uint32_t* directory, /* fill cores x RM_DIR_WORDS, zeroed before */
    rm_mark* marks,
    uint32_t* marks_written
);

/* Each item's base word: its first record's slot (0 for none) | 1 + its tile's index
 * among the heavy tiles (0: not cut) << RM_BASE_SLOT_BITS. */
void rm_base(
    const rm_scratch* scratch,
    const rm_item* items,
    uint32_t items_found,
    uint32_t* base
);

/* Setup core `core`'s first slot of item `item` at
 * next_slots[core * next_stride + item], items [first_item, end_item). */
void rm_next(
    const uint32_t* counters,
    const uint16_t* histograms,
    uint32_t setup_cores,
    uint32_t heavy_count,
    rm_scratch* scratch,
    const rm_item* items,
    uint32_t first_item,
    uint32_t end_item,
    uint32_t* next_slots,
    uint32_t next_stride
);

/* The whole step in turn: rm_costs and rm_pick ... */
uint32_t rm_heavy(
    const uint32_t* counters,
    uint32_t setup_cores,
    uint32_t fill_cores,
    rm_scratch* scratch,
    uint32_t* heavy,
    uint32_t* bands
);

/* ... then rm_clear, rm_hist, rm_layout and rm_next (0 also when the items pass
 * next_stride). */
uint32_t rm_middle(
    const uint32_t* counters,
    const uint16_t* histograms,
    uint32_t setup_cores,
    uint32_t fill_cores,
    const uint32_t* heavy,
    const uint32_t* bands,
    uint32_t heavy_count,
    rm_scratch* scratch,
    rm_item* items,
    uint32_t* items_found,
    uint32_t* tile_item,
    uint32_t* directory,
    rm_mark* marks,
    uint32_t* marks_written,
    uint32_t* next_slots,
    uint32_t next_stride
);
