/* The raster unit: its set-up, and a layer of a view, its commands built by the
 * generated header's builders (DR_RASTER_BUILD), its times and results the layer's. */
#include "raster_unit.h"

/* The middle pass's parts on the four cores: each a quarter of the tiles or items. */
typedef struct {
    const uint32_t* counters;
    uint32_t rows_at, item_count, tiles;
    raster_work_t* work;
} part_t;

static void costs_part(int core, void* arg) {
    const part_t* part = (const part_t*)arg;
    const uint32_t quarter = (uint32_t)core;
    rm_costs(
        part->counters,
        part->rows_at,
        1,
        &part->work->scratch,
        part->tiles * quarter / 4,
        part->tiles * (quarter + 1) / 4
    );
}

static void sort_part(int core, void* arg) {
    const part_t* part = (const part_t*)arg;
    const uint32_t quarter = (uint32_t)core;
    rm_sort(
        &part->work->scratch,
        part->item_count * quarter / 4,
        part->item_count * (quarter + 1) / 4
    );
}

/* the quarters in halves on cores 0 and 1 */
static void merge_part(int core, void* arg) {
    const part_t* part = (const part_t*)arg;
    const uint32_t quarter = (uint32_t)core;
    if (quarter < 2) {
        rm_merge(
            &part->work->scratch,
            part->item_count * 2 * quarter / 4,
            part->item_count * (2 * quarter + 1) / 4,
            part->item_count * (2 * quarter + 2) / 4
        );
    }
}

static raster_work_t* work_of(void) {
    return (raster_work_t*)DR_REGION(DR_RASTER_REGION_WORK);
}

/* The bank address of the camera area `area` (its first page). */
static uint32_t area_address(uint32_t area) {
    return DR_ADDRESS(DR_RASTER_REGION_CAMERA) + area * RASTER_K_AREA_PAGE_BYTES;
}

uint32_t raster_unit_setup(dr_frame_t* frame) {
    if (frame->bytes[DR_RASTER_REGION_WORK] < sizeof(raster_work_t)) {
        return RASTER_SMALL_REGION;
    }
    raster_work_t* work = work_of();
    for (uint32_t area = 0; area < RASTER_AREAS; area++) {
        work->ranged[area] = work->ready[area] = 0;
    }
    /* lines an earlier image left dirty would be written over what the cores write */
    kmx_flush(DR_RASTER_REGION_SUMS);
    kmx_flush(DR_RASTER_REGION_CAMERA);
    km_command_t command;
    DR_RASTER_BUILD(load_empty)(&command, 0, 0, frame->workers);
    return dr_run(&command);
}

/* The frame's tensors of the layer into a command's words. */
static void layer_word(
    km_command_t* command, uint32_t place, const dr_layer_t* layer, uint32_t column
) {
    dr_word(command, place, layer->words[column]);
}

/* COUNT over the cores' ranges; the next ranges set first unless FILL set them. */
static uint32_t count(
    dr_frame_t* frame,
    const dr_view_t* view,
    const dr_layer_t* layer,
    uint32_t area_index,
    uint32_t area
) {
    raster_work_t* work = work_of();
    raster_view_page(view, area);
    if (!work->ready[area_index]) {
        const uint32_t code = raster_ranges(frame, work, layer, area_index, area);
        if (code) {
            return code;
        }
    }
    work->ready[area_index] = 0;
    km_command_t command;
    DR_RASTER_BUILD(count)(&command, 0, 0, frame->cores, view->grid);
    dr_word(&command, DR_PLACE(COUNT_CAMERA), area_address(area));
    layer_word(&command, DR_PLACE(COUNT_MESH), layer, DR_RASTER_L_MESH);
    layer_word(&command, DR_PLACE(COUNT_PROFILE), layer, DR_RASTER_L_PROFILE);
    dr_word(&command, DR_PLACE(COUNT_HEAVY), 0); /* a first COUNT */
    return dr_run(&command);
}

/* The tiles to cut from SUM's totals: their count, written to the heavy region. */
static uint32_t pick(
    dr_frame_t* frame,
    const dr_view_t* view,
    const dr_layer_t* layer,
    part_t* part,
    uint32_t sum_tiles,
    uint32_t* heavy_count
) {
    raster_work_t* work = work_of();
    part->counters = (const uint32_t*)DR_REGION(DR_RASTER_REGION_SUMS);
    part->rows_at = sum_tiles; /* the totals, as one core's counters */
    part->tiles = view->tiles;
    part->work = work;
    if (dr_parallel(costs_part, part)) {
        return DR_PARALLEL;
    }
    *heavy_count = rm_pick(
        &work->scratch, frame->workers, work->heavy, work->bands, view->tiles
    );
    *dr_layer_time(frame, layer, DR_RASTER_R_HEAVY_TILES) = *heavy_count;
    if (*heavy_count > RM_MAX_HEAVY) {
        return RASTER_TOO_MANY_HEAVY;
    }
    if (*heavy_count) {
        volatile uint32_t* words = (volatile uint32_t*)DR_REGION(
            DR_RASTER_REGION_HEAVY
        );
        words[0] = *heavy_count;
        for (uint32_t index = 0; index < *heavy_count; index++) {
            words[1 + index] = work->heavy[index];
        }
        dr_flush(
            DR_RASTER_REGION_HEAVY, DR_RASTER_REGION_HEAVY_AT, RASTER_K_HEAVY_BYTES
        );
    }
    return 0;
}

/* HIST (after COUNT again in the recount), HSUM, and their sums into the scratch. */
static uint32_t histograms(
    dr_frame_t* frame,
    const dr_view_t* view,
    const dr_layer_t* layer,
    uint32_t area,
    uint32_t heavy_count,
    uint32_t sum_tiles,
    uint64_t* mark
) {
    km_command_t command;
    uint32_t code = 0;
#ifdef RASTER_RECOUNT
    /* the histograms not kept by COUNT: COUNT again, the heavy tiles' alone */
    DR_RASTER_BUILD(count)(&command, 0, 0, frame->cores, view->grid);
    dr_word(&command, DR_PLACE(COUNT_CAMERA), area_address(area));
    layer_word(&command, DR_PLACE(COUNT_MESH), layer, DR_RASTER_L_MESH);
    dr_word(&command, DR_PLACE(COUNT_PROFILE), 0); /* COUNT's profile: the first's */
    code = dr_run(&command);
    if (code) {
        return code;
    }
#else
    (void)view;
    (void)area;
#endif
    DR_RASTER_BUILD(hist)(&command, 0, 0, frame->cores, RASTER_K_HIST_PAGE_BYTES);
    layer_word(&command, DR_PLACE(HIST_PROFILE), layer, DR_RASTER_L_PROFILE);
    code = dr_run(&command);
    *dr_layer_time(frame, layer, DR_RASTER_T_HIST) += dr_ticks(mark);
    if (code) {
        return code;
    }
    const uint32_t slices = sum_tiles / RASTER_K_SLICE_TILES;
    DR_RASTER_BUILD(hsum)(
        &command, 0, 0, frame->workers, heavy_count, frame->cores, slices
    );
    code = dr_run(&command);
    *dr_layer_time(frame, layer, DR_RASTER_T_HSUM) += dr_ticks(mark);
    if (code) {
        return code;
    }
    const uint32_t heavy_words = 2 * RM_GROUPS;
    dr_invalidate(
        DR_RASTER_REGION_SUMS,
        DR_RASTER_REGION_SUMS_AT + 8u * sum_tiles,
        4u * heavy_words * heavy_count
    );
    const uint32_t* sums = (const uint32_t*)DR_REGION(DR_RASTER_REGION_SUMS);
    const uint32_t* heavy_sums = sums + 2 * sum_tiles; /* HSUM's, after the rows */
    raster_work_t* work = work_of();
    for (uint32_t index = 0; index < heavy_count; index++) {
        for (uint32_t group = 0; group < heavy_words; group++) {
            work->scratch
                .histograms[index][group] = heavy_sums[heavy_words * index + group];
        }
    }
    *dr_layer_time(frame, layer, DR_RASTER_T_TAKE) += dr_ticks(mark);
    return 0;
}

/* The items region's pages for PLACE and SETUP: tiles' words, rows, the addresses and
 * the frame words; the parts written given back. */
static uint32_t items_pages(
    dr_frame_t* frame,
    const dr_view_t* view,
    const dr_layer_t* layer,
    uint32_t item_count,
    uint64_t* mark
) {
    raster_work_t* work = work_of();
    uint32_t* items = (uint32_t*)DR_REGION(DR_RASTER_REGION_ITEMS);
    for (uint32_t i = 0; i < view->tiles; i++) { /* the frame's tiles alone */
        const uint32_t first = work->scratch.tile_item[i];
        items[i] = first | (work->scratch.tile_item[i + 1] - first) << 16;
    }
    uint16_t* rows = (uint16_t*)(items + RASTER_K_ITEM_ROWS / 4);
    for (uint32_t i = 0; i < item_count; i++) {
        const rm_item* item = &work->scratch.items[i];
        rows[i] = (uint16_t)(item->first_row | item->end_row << 8);
    }
    items[RASTER_K_HPREFIX_ADDR_AT / 4] = DR_LOAD_WORD(HPREFIX);
    items[RASTER_K_SHADE_ADDR_AT / 4] = layer->words[DR_RASTER_L_SHADE]; /* 0: not
                                                                            shaded */
    uint32_t* frame_words = items + RASTER_K_FRAME_WORDS_AT / 4;
    frame_words[0] = layer->words[DR_RASTER_L_FRAME_PAGES];
    for (
        uint32_t slot = 0; slot < DR_RASTER_L_FRAME_14 - DR_RASTER_L_FRAME_0 + 1; slot++
    ) {
        frame_words[1 + slot] = layer->words[DR_RASTER_L_FRAME_0 + slot];
    }
    *dr_layer_time(frame, layer, DR_RASTER_T_PAGES) += dr_ticks(mark);
    dr_sweep_t sweep;
    dr_sweep_start(&sweep, DR_RASTER_REGION_ITEMS);
    const uint32_t at = DR_RASTER_REGION_ITEMS_AT;
    dr_sweep_halves(
        &sweep, at + RASTER_K_ITEM_WORDS_AT, 4u * RM_ITEM_WORDS * item_count
    );
    dr_sweep_add(&sweep, at, 4u * view->tiles);
    dr_sweep_add(&sweep, at + RASTER_K_BASE_AT, 4u * item_count);
    dr_sweep_add(&sweep, at + RASTER_K_ITEM_ROWS, 2u * item_count);
    dr_sweep_add(
        &sweep, at + RASTER_K_CORE_WORDS_AT, 4u * RM_CORE_WORDS * frame->workers
    );
    dr_sweep_add(
        &sweep,
        at + RASTER_K_HPREFIX_ADDR_AT,
        RASTER_K_ITEM_WORDS_AT - RASTER_K_HPREFIX_ADDR_AT
    );
    const uint32_t code = dr_sweep_run(&sweep);
    *dr_layer_time(frame, layer, DR_RASTER_T_GIVE) += dr_ticks(mark);
    return code;
}

/* The middle pass: items, cores, the lists' layout for PLACE, the base slots; its list
 * slots in `slots`. */
static uint32_t middle(
    dr_frame_t* frame,
    const dr_view_t* view,
    const dr_layer_t* layer,
    part_t* part,
    uint32_t heavy_count,
    uint32_t* slots,
    uint64_t* mark
) {
    raster_work_t* work = work_of();
    const uint32_t workers = frame->workers;
    uint32_t item_count = 0;
    if (!rm_items(
            work->heavy,
            work->bands,
            heavy_count,
            &work->scratch,
            work->scratch.items,
            &item_count,
            work->scratch.tile_item,
            view->tiles
        )) {
        return RASTER_NO_LAYOUT;
    }
    *dr_layer_time(frame, layer, DR_RASTER_T_CUT) += dr_ticks(mark);
    part->item_count = item_count;
    if (dr_parallel(sort_part, part) || dr_parallel(merge_part, part)) {
        return DR_PARALLEL;
    }
    rm_merge(&work->scratch, 0, item_count / 2, item_count);
    *dr_layer_time(frame, layer, DR_RASTER_T_SORT) += dr_ticks(mark);
    if (!rm_owners(workers, &work->scratch, item_count)) {
        return RASTER_NO_LAYOUT;
    }
    *dr_layer_time(frame, layer, DR_RASTER_T_ASSIGN) += dr_ticks(mark);
    uint32_t* items = (uint32_t*)DR_REGION(DR_RASTER_REGION_ITEMS);
    *slots = rm_compact(
        workers,
        &work->scratch,
        work->scratch.items,
        item_count,
        items + RASTER_K_ITEM_WORDS_AT / 4,
        items + RASTER_K_CORE_WORDS_AT / 4
    );
    uint32_t mark_count = workers;
    for (uint32_t i = 0; i < item_count; i++) {
        mark_count += work->scratch.items[i].total != 0;
    }
    *dr_layer_time(frame, layer, DR_RASTER_R_SLOTS) = *slots;
    *dr_layer_time(frame, layer, DR_RASTER_R_ITEMS) = item_count;
    *dr_layer_time(frame, layer, DR_RASTER_R_MARKS) = mark_count;
    if (*slots == 0 || item_count > RASTER_K_SLOTS_BYTES / 4) {
        return RASTER_NO_LAYOUT;
    }
    if (*slots > layer->words[DR_RASTER_L_LIST_SLOTS] ||
        *slots >= 1u << RM_BASE_SLOT_BITS) {
        return RASTER_LISTS_SMALL;
    }
    rm_base(
        &work->scratch, work->scratch.items, item_count, items + RASTER_K_BASE_AT / 4
    );
    *dr_layer_time(frame, layer, DR_RASTER_T_COMPACT) += dr_ticks(mark);
    return items_pages(frame, view, layer, item_count, mark);
}

/* COUNT to the middle pass, as far as `steps` says: 0, or the code; `go` 0 when the
 * steps end there. */
static uint32_t first_half(
    dr_frame_t* frame,
    const dr_view_t* view,
    const dr_layer_t* layer,
    uint32_t area_index,
    uint32_t area,
    uint32_t* slots,
    uint64_t* mark
) {
    const uint32_t steps = dr_number(frame, DR_RASTER_N_STEPS);
    uint32_t code = count(frame, view, layer, area_index, area);
    *dr_layer_time(frame, layer, DR_RASTER_T_COUNT) += dr_ticks(mark);
    if (code || steps < 2) {
        return code;
    }
    /* SUM: the counters' totals, and each core's entries before it per tile */
    const uint32_t sum_tiles = (view->tiles + RASTER_K_SLICE_TILES - 1) /
        RASTER_K_SLICE_TILES * RASTER_K_SLICE_TILES;
    km_command_t command;
    DR_RASTER_BUILD(sum)(
        &command, 0, 0, frame->workers, frame->cores, sum_tiles / RASTER_K_SLICE_TILES
    );
    code = dr_run(&command);
    *dr_layer_time(frame, layer, DR_RASTER_T_SUM) += dr_ticks(mark);
    if (code) {
        return code;
    }
    /* the tiles to cut: the frame's tiles' entries, then their rows (SUM's slices) */
    dr_sweep_t sweep;
    dr_sweep_start(&sweep, DR_RASTER_REGION_SUMS);
    dr_sweep_halves(&sweep, DR_RASTER_REGION_SUMS_AT, 4u * sum_tiles);
    dr_sweep_halves(&sweep, DR_RASTER_REGION_SUMS_AT + 4u * sum_tiles, 4u * sum_tiles);
    if (dr_sweep_run(&sweep)) {
        return DR_PARALLEL;
    }
    *dr_layer_time(frame, layer, DR_RASTER_T_TAKE) += dr_ticks(mark);
    part_t part;
    uint32_t heavy_count = 0;
    code = pick(frame, view, layer, &part, sum_tiles, &heavy_count);
    *dr_layer_time(frame, layer, DR_RASTER_T_HEAVY) += dr_ticks(mark);
    if (code) {
        return code;
    }
    if (heavy_count) {
        code = histograms(frame, view, layer, area, heavy_count, sum_tiles, mark);
        if (code) {
            return code;
        }
    }
    code = middle(frame, view, layer, &part, heavy_count, slots, mark);
    const uint32_t parts[] = {
        DR_RASTER_T_TAKE,
        DR_RASTER_T_HEAVY,
        DR_RASTER_T_CUT,
        DR_RASTER_T_SORT,
        DR_RASTER_T_ASSIGN,
        DR_RASTER_T_COMPACT,
        DR_RASTER_T_PAGES,
        DR_RASTER_T_GIVE,
    };
    uint32_t* middle_time = dr_layer_time(frame, layer, DR_RASTER_T_MIDDLE);
    *middle_time = 0;
    for (uint32_t index = 0; index < sizeof parts / sizeof parts[0]; index++) {
        *middle_time += *dr_layer_time(frame, layer, parts[index]);
    }
    return code;
}

/* SETUP of the layer into `command`: the shaded one with the layer's shade blocks when
 * its column names them. */
static void setup(
    const dr_frame_t* frame,
    const dr_layer_t* layer,
    km_command_t* command,
    uint32_t area,
    uint32_t slots
) {
    const uint32_t shade = layer->words[DR_RASTER_L_SHADE];
    const uint32_t list_slots = slots | RASTER_K_SETUP_PREFIX;
    if (shade) {
        DR_RASTER_BUILD(setup_shaded)(command, 0, 0, frame->cores, list_slots);
        dr_word(command, DR_PLACE(SETUP_SHADED_SHADE), shade);
        dr_word(command, DR_PLACE(SETUP_SHADED_CAMERA), area_address(area));
        layer_word(command, DR_PLACE(SETUP_SHADED_MESH), layer, DR_RASTER_L_MESH);
        layer_word(command, DR_PLACE(SETUP_SHADED_LISTS), layer, DR_RASTER_L_LISTS);
        layer_word(command, DR_PLACE(SETUP_SHADED_PROFILE), layer, DR_RASTER_L_PROFILE);
        return;
    }
    DR_RASTER_BUILD(setup)(command, 0, 0, frame->cores, list_slots);
    dr_word(command, DR_PLACE(SETUP_CAMERA), area_address(area));
    layer_word(command, DR_PLACE(SETUP_MESH), layer, DR_RASTER_L_MESH);
    layer_word(command, DR_PLACE(SETUP_LISTS), layer, DR_RASTER_L_LISTS);
    layer_word(command, DR_PLACE(SETUP_PROFILE), layer, DR_RASTER_L_PROFILE);
}

uint32_t raster_unit_layer(
    dr_frame_t* frame, const dr_view_t* view, const dr_layer_t* layer
) {
    if (view->tiles > RM_TILES) {
        return RASTER_BAD_GRID;
    }
    uint64_t mark = kmx_time();
    raster_work_t* work = work_of();
    rm_lay(&work->scratch, view->tiles); /* the middle pass's arrays: the frame's */
    const uint32_t area_index = view->index * DR_LAYERS + layer->index;
    const uint32_t area = area_index * RASTER_K_AREA_PAGES;
    const uint32_t steps = dr_number(frame, DR_RASTER_N_STEPS);
    uint32_t slots = 0;
    uint32_t code = first_half(frame, view, layer, area_index, area, &slots, &mark);
    if (code || steps < 3) {
        return code;
    }
    /* PLACE, then SETUP */
    km_command_t command;
    DR_RASTER_BUILD(place)(&command, 0, 0, frame->workers, frame->workers, view->grid);
    layer_word(&command, DR_PLACE(PLACE_DIRECTORY), layer, DR_RASTER_L_DIRECTORY);
    layer_word(&command, DR_PLACE(PLACE_LISTS), layer, DR_RASTER_L_LISTS);
    layer_word(&command, DR_PLACE(PLACE_PROFILE), layer, DR_RASTER_L_PROFILE);
    code = dr_run(&command);
    *dr_layer_time(frame, layer, DR_RASTER_T_PLACE) += dr_ticks(&mark);
    if (code) {
        return code;
    }
    setup(frame, layer, &command, area, slots);
    code = dr_run(&command);
    *dr_layer_time(frame, layer, DR_RASTER_T_SETUP) += dr_ticks(&mark);
    if (code || steps < 4) {
        return code;
    }
    /* FILL; the next frame's ranges while the grid fills: COUNT and SETUP are done */
    DR_RASTER_BUILD(fill)(&command, 0, 0, frame->workers, view->grid);
    layer_word(&command, DR_PLACE(FILL_DIRECTORY), layer, DR_RASTER_L_DIRECTORY);
    layer_word(&command, DR_PLACE(FILL_LISTS), layer, DR_RASTER_L_LISTS);
    layer_word(&command, DR_PLACE(FILL_FRAME), layer, DR_RASTER_L_FRAME_0);
    layer_word(&command, DR_PLACE(FILL_PROFILE), layer, DR_RASTER_L_FILL_PROFILE);
    uint32_t handle;
    code = dr_submit(&command, &handle);
    if (code == 0) {
        const uint32_t ranged = raster_ranges(frame, work, layer, area_index, area);
        work->ready[area_index] = ranged == 0;
        code = dr_wait(handle);
        code = code ? code : ranged;
    }
    *dr_layer_time(frame, layer, DR_RASTER_T_FILL) += dr_ticks(&mark);
    return code;
}
