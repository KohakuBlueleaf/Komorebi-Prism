/* The middle pass's functions the thread calls (raster_middle.h): tiles over RM_SPLIT
 * of the mean cut; items by falling cost to the least loaded core (ties: lower). */
#include "raster_middle.h"

/* Stable merge sort of order by falling key, through spare. */
static void sort_desc(
    uint32_t* order, uint32_t* spare, const uint64_t* key, uint32_t count
) {
    for (uint32_t width = 1; width < count; width *= 2) {
        for (uint32_t first = 0; first < count; first += 2 * width) {
            uint32_t middle = first + width < count ? first + width : count;
            uint32_t end = first + 2 * width < count ? first + 2 * width : count;
            uint32_t left = first, right = middle, merged = first;
            while (left < middle && right < end) {
                spare[merged++] =
                    (key[order[right]] > key[order[left]] ? order[right++]
                                                          : order[left++]);
            }
            while (left < middle) {
                spare[merged++] = order[left++];
            }
            while (right < end) {
                spare[merged++] = order[right++];
            }
        }
        for (uint32_t position = 0; position < count; position++) {
            order[position] = spare[position];
        }
    }
}

/* Restores the heap of keys (load << 8 | core: by load, ties by core) after its
 * first key grew. */
static void sift_down(uint64_t* heap, uint32_t count) {
    uint32_t position = 0;
    const uint64_t moved = heap[0];
    for (;;) {
        const uint32_t left = 2 * position + 1, right = left + 1;
        if (left >= count) {
            break;
        }
        const uint32_t
            smaller = (right < count && heap[right] < heap[left] ? right : left);
        if (heap[smaller] >= moved) {
            break;
        }
        heap[position] = heap[smaller];
        position = smaller;
    }
    heap[position] = moved;
}

/* `bytes` from *at (whole 8 bytes), *at moved past them. */
static void* take(uint8_t** at, uint64_t bytes) {
    void* taken = *at;
    *at += (bytes + 7u) & ~(uint64_t)7u;
    return taken;
}

void rm_lay(rm_scratch* scratch, uint32_t tiles) {
    const uint64_t items = tiles + RM_BAND_ITEMS;
    uint8_t* at = (uint8_t*)scratch->space;
    scratch->entries = take(&at, 8 * (uint64_t)tiles);
    scratch->rows = take(&at, 8 * (uint64_t)tiles);
    scratch->tile_cost = take(&at, 8 * (uint64_t)tiles);
    scratch->cost = take(&at, 8 * items); /* the sort's key, beside its orders */
    scratch->order = take(&at, 4 * items);
    scratch->spare_order = take(&at, 4 * items);
    scratch->owner = take(&at, 4 * items);
    scratch->header = take(&at, 4 * items);
    scratch->load = take(&at, 8 * RM_MAX_CORES);
    scratch->heap = take(&at, 8 * RM_MAX_CORES);
    scratch->first_item = take(&at, 4 * (RM_MAX_CORES + 1));
    scratch->next_slot = take(&at, 4 * items);
    scratch->histograms = take(&at, 8 * 2 * RM_GROUPS * RM_MAX_HEAVY);
    scratch->heavy_of = take(&at, 4 * (uint64_t)tiles);
    scratch->slot_counts = take(&at, 4 * RM_MAX_CORES);
    scratch->item_counts = take(&at, 4 * RM_MAX_CORES);
    scratch->items = take(&at, sizeof(rm_item) * items);
    scratch->tile_item = take(&at, 4 * ((uint64_t)tiles + 1));
    scratch->laid = tiles;
}

void rm_costs(
    const uint32_t* counters,
    uint32_t rows_at,
    uint32_t cores,
    rm_scratch* scratch,
    uint32_t first_tile,
    uint32_t end_tile
) {
    for (uint32_t tile = first_tile; tile < end_tile; tile++) {
        scratch->entries[tile] = scratch->rows[tile] = 0;
    }
    /* core by core, so that the counters are read in order (a walk across the cores
     * per tile misses the cache at every step) */
    for (uint32_t core = 0; core < cores; core++) {
        const uint32_t* core_counters = counters + core * RM_COUNTERS;
        for (uint32_t tile = first_tile; tile < end_tile; tile++) {
            scratch->entries[tile] += core_counters[tile];
            scratch->rows[tile] += core_counters[rows_at + tile];
        }
    }
    for (uint32_t tile = first_tile; tile < end_tile; tile++) {
        const uint64_t tile_entries = scratch->entries[tile];
        const uint64_t tile_rows = scratch->rows[tile];
        scratch->tile_cost[tile] =
            (tile_entries
                 ? RM_COST_TRI * tile_entries + RM_COST_ROW * tile_rows + RM_COST_TILE
                 : RM_COST_EMPTY);
    }
}

uint32_t rm_pick(
    rm_scratch* scratch,
    uint32_t fill_cores,
    uint32_t* heavy,
    uint32_t* bands,
    uint32_t tiles
) {
    uint64_t total_cost = 0, max = 0;
    for (uint32_t tile = 0; tile < tiles; tile++) {
        total_cost += scratch->tile_cost[tile];
        max = scratch->tile_cost[tile] > max ? scratch->tile_cost[tile] : max;
    }
    const double mean = (double)total_cost / (double)fill_cores;
    if ((double)max <= mean) {
        return 0;
    }
    const double target = RM_SPLIT * mean;
    uint32_t heavy_found = 0;
    for (uint32_t tile = 0; tile < tiles; tile++) {
        const double ratio = (double)scratch->tile_cost[tile] / target;
        uint32_t tile_bands = (uint32_t)ratio;
        tile_bands += (double)tile_bands < ratio;
        tile_bands = tile_bands < RM_MAX_BANDS ? tile_bands : RM_MAX_BANDS;
        if (tile_bands >= 2) {
            if (heavy_found < RM_MAX_HEAVY) {
                heavy[heavy_found] = tile;
                bands[heavy_found] = tile_bands;
            }
            heavy_found++;
        }
    }
    return heavy_found;
}

/* Band bounds (rows) of one heavy tile from its counts summed over the cores. */
static uint32_t cut(
    const uint64_t* starts, const uint64_t* ends, uint32_t bands, uint32_t* bounds
) {
    uint64_t cumulative[RM_GROUPS], running = 0, starts_so_far = 0, ends_so_far = 0;
    for (uint32_t group = 0; group < RM_GROUPS; group++) {
        starts_so_far += starts[group];
        const uint64_t cover = starts_so_far -
            ends_so_far; /* starts so far, less ends before group */
        ends_so_far += ends[group];
        running += 2 * RM_COST_ROW * cover + RM_COST_TRI * starts[group];
        cumulative[group] = running;
    }
    uint32_t count = 0;
    bounds[count++] = 0;
    for (uint32_t band = 1; band < bands; band++) {
        uint32_t group = 0;
        while (
            group < RM_GROUPS &&
            bands * cumulative[group] < cumulative[RM_GROUPS - 1] * band
        ) {
            group++;
        }
        const uint32_t row = 2 * (group + 1);
        if (row > bounds[count - 1] && row < 2 * RM_GROUPS) {
            bounds[count++] = row;
        }
    }
    bounds[count++] = 2 * RM_GROUPS;
    return count - 1;
}

uint32_t rm_items(
    const uint32_t* heavy,
    const uint32_t* bands,
    uint32_t heavy_count,
    rm_scratch* scratch,
    rm_item* items,
    uint32_t* items_found,
    uint32_t* tile_item,
    uint32_t tiles
) {
    if (heavy_count > RM_MAX_HEAVY || tiles > scratch->laid) {
        return 0;
    }
    for (uint32_t tile = 0; tile < tiles; tile++) { /* the frame's tiles alone */
        scratch->heavy_of[tile] = -1;
    }
    for (uint32_t heavy_index = 0; heavy_index < heavy_count; heavy_index++) {
        scratch->heavy_of[heavy[heavy_index]] = (int32_t)heavy_index;
    }
    /* items in tile order, with their entries and costs */
    uint32_t item_count = 0;
    for (uint32_t tile = 0; tile < tiles; tile++) {
        tile_item[tile] = item_count;
        const int32_t heavy_index = scratch->heavy_of[tile];
        if (heavy_index < 0) {
            items[item_count] = (rm_item){
                tile, 0, 32, (uint32_t)scratch->entries[tile]
            };
            scratch->cost[item_count++] = scratch->tile_cost[tile];
            continue;
        }
        const uint64_t* starts = scratch->histograms[heavy_index];
        const uint64_t* ends = starts + RM_GROUPS;
        uint32_t bounds[RM_MAX_BANDS + 1];
        const uint32_t band_total = cut(starts, ends, bands[heavy_index], bounds);
        if (item_count + band_total + tiles - 1 - tile > RM_MAX_ITEMS) {
            return 0;
        }
        for (uint32_t band = 0; band < band_total; band++) {
            const uint32_t first_row = bounds[band], end_row = bounds[band + 1];
            uint64_t entries = 0, cover = 0, starts_so_far = 0, ends_so_far = 0;
            for (uint32_t group = 0; group < end_row / 2; group++) {
                entries += starts[group]; /* starting before end_row, less ending before
                                             first_row */
                entries -= group < first_row / 2 ? ends[group] : 0;
                starts_so_far += starts[group];
                if (group >= first_row / 2) {
                    cover += starts_so_far - ends_so_far;
                }
                ends_so_far += ends[group];
            }
            items[item_count] = (rm_item){tile, first_row, end_row, (uint32_t)entries};
            scratch->cost[item_count++] =
                (entries
                     ? RM_COST_TRI * entries + RM_COST_ROW * 2 * cover + RM_COST_TILE
                     : RM_COST_EMPTY);
        }
    }
    tile_item[tiles] = item_count; /* the last tile's end; beyond the grid: none */
    *items_found = item_count;
    return 1;
}

void rm_sort(rm_scratch* scratch, uint32_t first, uint32_t end) {
    for (uint32_t i = first; i < end; i++) {
        scratch->order[i] = i;
    }
    sort_desc(
        scratch->order + first, scratch->spare_order + first, scratch->cost, end - first
    );
}

void rm_merge(rm_scratch* scratch, uint32_t first, uint32_t middle, uint32_t end) {
    const uint64_t* cost = scratch->cost;
    uint32_t* order = scratch->order;
    uint32_t left = first, right = middle, merged = first;
    while (left < middle && right < end) {
        scratch->spare_order[merged++] =
            (cost[order[right]] > cost[order[left]] ? order[right++] : order[left++]);
    }
    while (left < middle) {
        scratch->spare_order[merged++] = order[left++];
    }
    while (right < end) {
        scratch->spare_order[merged++] = order[right++];
    }
    for (uint32_t position = first; position < end; position++) {
        order[position] = scratch->spare_order[position];
    }
}

uint32_t rm_owners(uint32_t fill_cores, rm_scratch* scratch, uint32_t item_count) {
    if (fill_cores == 0 || fill_cores > RM_MAX_CORES) {
        return 0;
    }
    /* the least loaded core (ties: the lower) from a heap of load << 8 | core; a core
     * with RM_DIR_MAX_ITEMS (first_item counts; rm_layout sets it after) goes last */
    uint64_t* heap = scratch->heap;
    for (uint32_t core = 0; core < fill_cores; core++) {
        heap[core] = core;
        scratch->load[core] = 0;
        scratch->first_item[core] = 0;
    }
    for (uint32_t rank = 0; rank < item_count; rank++) {
        const uint32_t item = scratch->order[rank], core = (uint32_t)(heap[0] & 0xFF);
        scratch->owner[item] = core;
        scratch->load[core] += scratch->cost[item];
        heap[0] =
            (++scratch->first_item[core] < RM_DIR_MAX_ITEMS
                 ? heap[0] + (scratch->cost[item] << 8)
                 : (UINT64_MAX & ~(uint64_t)0xFF) | core);
        sift_down(heap, fill_cores);
    }
    return 1;
}

uint32_t rm_compact(
    uint32_t fill_cores,
    rm_scratch* scratch,
    const rm_item* items,
    uint32_t item_count,
    uint32_t* item_words,
    uint32_t* core_words
) {
    uint32_t* slot_counts = scratch->slot_counts;
    uint32_t* item_counts = scratch->item_counts;
    for (uint32_t core = 0; core < fill_cores; core++) {
        slot_counts[core] = item_counts[core] = 0;
    }
    for (uint32_t i = 0; i < item_count; i++) {
        const uint32_t core = scratch->owner[i];
        item_counts[core]++;
        slot_counts[core] += items[i].total ? 1 + items[i].total : 0;
    }
    uint32_t page = 0;
    for (uint32_t core = 0; core < fill_cores; core++) {
        if (item_counts[core] > RM_DIR_MAX_ITEMS) {
            return 0;
        }
        const uint32_t
            pages = ((slot_counts[core] + 1 + RM_PAGE_SLOTS - 1) / RM_PAGE_SLOTS);
        uint32_t* words = core_words + RM_CORE_WORDS * core;
        words[0] = page;
        words[1] = pages;
        words[2] = item_counts[core];
        words[3] = RM_PAGE_SLOTS * page + slot_counts[core]; /* the end slot */
        slot_counts[core] = RM_PAGE_SLOTS * page; /* from here: the next header */
        page += pages;
    }
    for (uint32_t i = 0; i < item_count; i++) {
        const uint32_t core = scratch->owner[i], total = items[i].total;
        scratch->header[i] = total ? slot_counts[core] : 0;
        item_words[RM_ITEM_WORDS * i] = core | total << 8;
        item_words[RM_ITEM_WORDS * i + 1] = scratch->header[i];
        slot_counts[core] += total ? 1 + total : 0;
    }
    return RM_PAGE_SLOTS * page;
}

void rm_base(
    const rm_scratch* scratch, const rm_item* items, uint32_t item_count, uint32_t* base
) {
    for (uint32_t i = 0; i < item_count; i++) {
        const int32_t heavy_index = scratch->heavy_of[items[i].tile];
        base[i] =
            ((items[i].total ? scratch->header[i] + 1 : 0) |
             (heavy_index < 0 ? 0 : (uint32_t)(heavy_index + 1) << RM_BASE_SLOT_BITS));
    }
}
