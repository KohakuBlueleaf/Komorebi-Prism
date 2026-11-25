/* The whole middle pass in turn (raster_middle.h), from the parts in raster_middle.c:
 * rm_heavy, then rm_middle. */
#include "raster_middle.h"

uint32_t rm_heavy(
    const uint32_t* counters,
    uint32_t setup_cores,
    uint32_t fill_cores,
    rm_scratch* scratch,
    uint32_t* heavy,
    uint32_t* bands
) {
    rm_lay(scratch, RM_TILES);
    rm_costs(counters, RM_TILES, setup_cores, scratch, 0, RM_TILES);
    return rm_pick(scratch, fill_cores, heavy, bands, RM_TILES);
}

void rm_clear(uint32_t* directory, uint32_t first_core, uint32_t end_core) {
    for (
        uint32_t word = first_core * RM_DIR_WORDS; word < end_core * RM_DIR_WORDS;
        word++
    ) {
        directory[word] = 0;
    }
}

/* Entries of a tile's group counts that reach rows [first_row, end_row). */
static uint64_t band_count(
    const uint16_t* starts, const uint16_t* ends, uint32_t first_row, uint32_t end_row
) {
    uint64_t entries = 0;
    for (uint32_t group = 0; group < end_row / 2; group++) {
        entries += starts[group];
    }
    for (uint32_t group = 0; group < first_row / 2; group++) {
        entries -= ends[group];
    }
    return entries;
}

void rm_hist(
    const uint16_t* histograms,
    uint32_t setup_cores,
    uint32_t heavy_count,
    rm_scratch* scratch
) {
    /* core by core (in memory order) */
    for (uint32_t heavy_index = 0; heavy_index < heavy_count; heavy_index++) {
        for (uint32_t group = 0; group < 2 * RM_GROUPS; group++) {
            scratch->histograms[heavy_index][group] = 0;
        }
    }
    for (uint32_t core = 0; core < setup_cores; core++) {
        const uint16_t*
            core_histograms = (histograms + core * heavy_count * 2 * RM_GROUPS);
        for (uint32_t heavy_index = 0; heavy_index < heavy_count; heavy_index++) {
            for (uint32_t group = 0; group < 2 * RM_GROUPS; group++) {
                scratch->histograms
                    [heavy_index]
                    [group] += (core_histograms[heavy_index * 2 * RM_GROUPS + group]);
            }
        }
    }
}

uint32_t rm_assign(uint32_t fill_cores, rm_scratch* scratch, uint32_t item_count) {
    rm_sort(scratch, 0, item_count);
    return rm_owners(fill_cores, scratch, item_count);
}

uint32_t rm_layout(
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
    uint32_t* marks_written
) {
    if (!rm_items(
            heavy, bands, heavy_count, scratch, items, items_found, tile_item, RM_TILES
        ) ||
        !rm_assign(fill_cores, scratch, *items_found)) {
        return 0;
    }
    const uint32_t item_count = *items_found;
    /* each core's items in item (tile) order */
    for (uint32_t core = 0; core <= fill_cores; core++) {
        scratch->first_item[core] = 0;
    }
    for (uint32_t i = 0; i < item_count; i++) {
        scratch->first_item[scratch->owner[i] + 1]++;
    }
    for (uint32_t core = 0; core < fill_cores; core++) {
        scratch->first_item[core + 1] += scratch->first_item[core];
    }
    for (uint32_t i = 0; i < item_count; i++) {
        scratch->spare_order[scratch->first_item[scratch->owner[i]]++] = i;
    }
    for (uint32_t core = fill_cores; core > 0; core--) {
        scratch->first_item[core] = scratch->first_item[core - 1];
    }
    scratch->first_item[0] = 0;
    /* each core's stream: headers, records, the end slot */
    uint32_t page = 0, mark_count = 0;
    for (uint32_t core = 0; core < fill_cores; core++) {
        uint32_t* directory_page = directory + core * RM_DIR_WORDS;
        uint32_t slot = RM_PAGE_SLOTS * page, own_items = 0;
        for (
            uint32_t rank = scratch->first_item[core];
            rank < scratch->first_item[core + 1];
            rank++
        ) {
            const uint32_t item_index = scratch->spare_order[rank];
            if (own_items == RM_DIR_MAX_ITEMS) {
                return 0;
            }
            const rm_item* item = &items[item_index];
            uint32_t id = item->tile;
            if (item->first_row != 0 || item->end_row != 32) {
                id |=
                    (item->first_row << RM_ITEM_ROW0_SHIFT |
                     item->end_row << RM_ITEM_ROW1_SHIFT);
            }
            if (item->total == 0) {
                directory_page[RM_DIR_IDS + own_items++] = id | RM_ITEM_EMPTY;
                continue;
            }
            directory_page[RM_DIR_IDS + own_items++] = id;
            scratch->header[item_index] = slot;
            marks[mark_count++] = (rm_mark){
                slot,
                RM_MARK_TILE,
                item->tile,
                item->total,
                item->first_row,
                item->end_row
            };
            slot += 1 + item->total;
        }
        marks[mark_count++] = (rm_mark){slot, RM_MARK_END, 0, 0, 0, 0};
        const uint32_t pages =
            ((slot + 1 - RM_PAGE_SLOTS * page + RM_PAGE_SLOTS - 1) / RM_PAGE_SLOTS);
        directory_page[RM_DIR_FIRST] = page;
        directory_page[RM_DIR_PAGES] = pages;
        directory_page[RM_DIR_ITEMS] = own_items;
        page += pages;
    }
    *marks_written = mark_count;
    return RM_PAGE_SLOTS * page;
}

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
) {
    for (uint32_t i = first_item; i < end_item; i++) {
        scratch->next_slot[i] = items[i].total ? scratch->header[i] + 1 : 0;
    }
    for (uint32_t core = 0; core < setup_cores; core++) {
        const uint32_t* core_counters = counters + core * RM_COUNTERS;
        uint32_t* core_next = next_slots + core * next_stride;
        for (uint32_t i = first_item; i < end_item; i++) {
            const rm_item* item = &items[i];
            core_next[i] = scratch->next_slot[i];
            if (item->total == 0) {
                continue;
            }
            const int32_t heavy_index = scratch->heavy_of[item->tile];
            if (heavy_index < 0) {
                scratch->next_slot[i] += core_counters[item->tile];
            } else {
                const uint16_t* core_histograms =
                    (histograms +
                     (core * heavy_count + (uint32_t)heavy_index) * 2 * RM_GROUPS);
                scratch->next_slot[i] += ((uint32_t)band_count(
                    core_histograms,
                    core_histograms + RM_GROUPS,
                    item->first_row,
                    item->end_row
                ));
            }
        }
    }
}

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
) {
    if (fill_cores > RM_MAX_CORES) {
        return 0;
    }
    if (heavy_count > RM_MAX_HEAVY) {
        return 0;
    }
    if (scratch->laid != RM_TILES) {
        rm_lay(scratch, RM_TILES);
    }
    rm_clear(directory, 0, fill_cores);
    rm_hist(histograms, setup_cores, heavy_count, scratch);
    const uint32_t slots = (rm_layout(
        fill_cores,
        heavy,
        bands,
        heavy_count,
        scratch,
        items,
        items_found,
        tile_item,
        directory,
        marks,
        marks_written
    ));
    if (slots == 0 || *items_found > next_stride) {
        return 0;
    }
    rm_next(
        counters,
        histograms,
        setup_cores,
        heavy_count,
        scratch,
        items,
        0,
        *items_found,
        next_slots,
        next_stride
    );
    return slots;
}
