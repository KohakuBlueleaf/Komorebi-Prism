/* A view as Komorebi's pulls (dispatch.h): the frame's page, then the phases asked:
 * count, sums, the slices' places, place, the steps' words, tiles. */
#include "dispatch.h"
#include "dispatch_cull.h"

/* The work handler's and the sums' commands carry the page as their block */
#define PAGE_BYTES (4u * TF_WORDS)

_Static_assert(TF_STEP_AT + DP_STEP_WORDS <= TF_WORDS, "the steps' words fit the page");
_Static_assert(PAGE_BYTES <= 1024u, "a command's block holds the page");
_Static_assert(DP_NEED_BYTES == 4u * DP_NEED_WORDS, "the need page's words");
_Static_assert(DP_NEED_ENTRIES + DR_LAYERS <= DP_NEED_WORDS, "the need page's layers");

/* A view's group and what its page does not hold: the group's first rank and cores,
 * the layers in the page, each one's list slots, row index and entries placed, the
 * count ranges, the slices and the slices a row of the grid */
typedef struct {
    uint32_t first, count, layers, ranges, slices, slices_across;
    uint32_t list_slots[TR_LAYERS], rows[TR_LAYERS], entries[TR_LAYERS];
    uint32_t groups[TR_LAYERS];
} view_t;

/* Whether the records, slices' words and lists hold the eye's view as the last COLOUR
 * view drew it whole: set by that view, cleared by any view that counts, any DEPTH
 * view and any view that ends with a code */
static uint32_t g_eye_held __attribute__((section(".data"))) = 0;

/* The count pull's deal of the view (dispatch_cull.h) and the groups' boxes'
 * generation the region was last read at (the number DP_N_CULL) */
static dp_cull_t g_cull __attribute__((section(".data"))) = {0};
static uint32_t g_boxes_seen __attribute__((section(".data"))) = 0;

static volatile uint32_t* page_of(void) {
    return (volatile uint32_t*)DR_REGION(DP_REGION_PAGE);
}

static dp_choose_t* choose_of(void) {
    return (dp_choose_t*)DR_REGION(DP_REGION_STATE);
}

uint32_t dp_setup(dr_frame_t* frame) {
    if (frame->bytes[DP_REGION_PAGE] < PAGE_BYTES ||
        frame->bytes[DP_REGION_STATE] < DP_CHOOSE_BYTES ||
        frame->bytes[DP_REGION_SLICES] < 4ull * TS_WORDS * DP_SLICES_MOST ||
        frame->bytes[DP_REGION_LOG] < KMX_PULL_LOG_BYTES(DP_RANGES_MOST) ||
        frame->bytes[DP_REGION_NEED] < DP_NEED_BYTES) {
        return DP_SMALL_REGION;
    }
    /* lines an earlier image left dirty would be written over what the cores write */
    kmx_flush(DP_REGION_SLICES);
    g_eye_held = 0;
    g_boxes_seen = 0;
    return 0;
}

/* The dispatcher's next wake event by `until`: 0, or 1 (late, stopped). */
static uint32_t wake(uint64_t until) {
    kmx_event event;
    while (kmx_time() < until && !kmx_stop_requested()) {
        if (kmx_poll(&event) == KMX_OK && event.kind == KMX_EVENT_WAKE) {
            return 0;
        }
    }
    return 1u;
}

/* `command` pulled by `settings` until its event, again after a full ring or a busy
 * rejection, within DR_WAIT_TICKS: 0, DP_PULL_BAD, or `late`. */
static uint32_t pull(
    const km_command_t* command, const kmx_pull* settings, uint32_t where, uint32_t late
) {
    kmx_progress(where);
    const uint64_t until = kmx_time() + DR_WAIT_TICKS;
    for (;;) {
        kmx_event event;
        event.handle = event.kind = event.auxiliary = event.ticks = 0;
        const int error = kmx_pull_run(command, settings, &event);
        if (error == KMX_FULL && event.handle != 0) {
            /* the command runs; its event waits behind 32 others */
            const int waited = kmx_wait(event.handle, until, &event);
            return waited == KMX_OK && event.kind == KM_EVENT_DONE ? 0u : late;
        }
        if (error == KMX_FULL && kmx_time() < until && !kmx_stop_requested()) {
            continue;
        }
        if (error == KMX_BAD) {
            return DP_PULL_BAD;
        }
        if (error != KMX_OK) {
            return late;
        }
        if (event.kind == KM_EVENT_DONE) {
            return 0;
        }
        if (event.kind == KM_EVENT_REJECTED && event.auxiliary == KMX_REJECT_BUSY &&
            wake(until) == 0) {
            continue;
        }
        return late;
    }
}

/* The page's words of the view and its layers (a DEPTH view: the layers with depth),
 * the group of every core; the count ranges. 0, or the code. */
static uint32_t view_page(const dr_frame_t* frame, const dr_view_t* view, view_t* out) {
    volatile uint32_t* page = page_of();
    const uint32_t range_blocks = dr_number(frame, DP_N_RANGE_BLOCKS);
    const uint32_t across = DP_GRID_ACROSS(view->grid);
    const uint32_t down = DP_GRID_DOWN(view->grid);
    if (range_blocks == 0 || across * down > 0xFFFFu) {
        return DP_BAD_NUMBERS;
    }
    out->first = 0;
    out->count = frame->cores;
    /* runs of DP_SLICE_TILES along a row (stages/raster/threads/layout.py slices_of) */
    out->slices_across = (across + DP_SLICE_TILES - 1u) / DP_SLICE_TILES;
    out->slices = out->slices_across * down;
    if (out->slices > DP_SLICES_MOST) {
        return DP_TOO_MANY;
    }
    for (uint32_t word = 0; word < TF_WORDS; word++) {
        page[word] = 0;
    }
    const uint32_t depth = view->kind == DR_VIEW_DEPTH;
    page[TF_VIEW] = view->index | (depth ? TV_DEPTH : TV_COLOUR) << 8;
    page[TF_GRID] = (view->grid & ~0xFu) | frame->bank_plus_one;
    page[TF_CAMERA] = view->camera_at;
    page[TF_RECORDS] = dr_number(frame, DP_N_RECORDS);
    page[TF_SLICES] = DR_ADDRESS(DP_REGION_SLICES);
    page[TF_SLICE_COUNT] = out->slices;
    page[TF_SLICE_TILES] = DP_SLICE_TILES;
    page[TF_HEAVY] = dr_number(frame, DP_N_HEAVY);
    page[TF_TARGET] = depth ? view->target : dr_number(frame, DP_N_DISPLAY);
    page[TF_PAGE_FIRST] = depth ? view->target_first : 0u;
    page[TF_PAGE_ACROSS] = depth ? view->target_across : across;
    page[TF_RANGE_BLOCKS] = range_blocks;
    page[TF_ACCOUNT] = dr_number(frame, DP_N_ACCOUNT);
    page[TF_ACCOUNT_RECORDS] = dr_number(frame, DP_N_ACCOUNT_RECORDS);
    const uint32_t row = DR_LAYER_WORDS * view->index * DR_LAYERS;
    dr_invalidate(DR_REGION_LAYERS, 4u * row, 4u * DR_LAYER_WORDS * frame->layers);
    const volatile uint32_t* rows = (const volatile uint32_t*)DR_REGION(
        DR_REGION_LAYERS
    );
    out->layers = out->ranges = 0;
    for (uint32_t layer = 0; layer < frame->layers; layer++) {
        const volatile uint32_t* words = rows + row + DR_LAYER_WORDS * layer;
        if (depth && !words[DR_L_DEPTH]) {
            continue;
        }
        if (out->layers == TR_LAYERS) {
            return DP_BAD_LAYERS;
        }
        volatile uint32_t* at = page + TF_LAYER_AT + TF_LAYER_WORDS * out->layers;
        const uint32_t blocks = words[DP_L_BLOCKS];
        at[TF_L_MESH] = words[DP_L_MESH];
        at[TF_L_RANGE_FIRST] = out->ranges;
        at[TF_L_BLOCKS] = blocks;
        at[TF_L_SHADE] = words[DP_L_SHADE];
        at[TF_L_LISTS] = words[DP_L_LISTS];
        at[TF_L_COUNTS] = words[DP_L_COUNTS];
        at[TF_L_ROWS] = words[DP_L_ROWS];
        at[TF_L_POSITIONS] = words[DP_L_POSITIONS];
        at[TF_L_BOXES] = words[DP_L_BOXES];
        out->rows[out->layers] = layer;
        out->groups[out->layers] = words[DP_L_GROUPS];
        out->list_slots[out->layers++] = words[DP_L_LIST_SLOTS];
        out->ranges += (blocks + range_blocks - 1u) / range_blocks;
    }
    page[TF_LAYER_COUNT] = out->layers;
    return out->ranges > DP_RANGES_MOST ? DP_TOO_MANY : 0u;
}

/* The count pull's deal of the view `one` when the number DP_N_CULL (the groups'
 * boxes' generation; 0: none) is set: its ranges and groups, its layers' first ranges,
 * groups and boxes, its camera and padded frame; the region read again at a new
 * generation; the groups tested, the survivors written. `culled` 1 when the deal is
 * culled. 0, DP_BAD_NUMBERS (no ranges a group, boxes past the region),
 * DP_SMALL_REGION, or the director's code. */
static uint32_t cull_view(
    const dr_frame_t* frame, const dr_view_t* view, const view_t* one, uint32_t* culled
) {
    const uint32_t generation = dr_number(frame, DP_N_CULL);
    const uint32_t group_ranges = dr_number(frame, DP_N_GROUP_RANGES);
    *culled = 0;
    if (generation == 0) {
        return 0;
    }
    const uint64_t bytes = frame->bytes[DP_REGION_GROUP_BOXES];
    if (group_ranges == 0) {
        return DP_BAD_NUMBERS;
    }
    if (generation != g_boxes_seen) {
        dr_invalidate(DP_REGION_GROUP_BOXES, DP_REGION_GROUP_BOXES_AT, (uint32_t)bytes);
        g_boxes_seen = generation;
    }
    const volatile uint32_t* page = page_of();
    g_cull.ranges = one->ranges;
    g_cull.group_ranges = group_ranges;
    g_cull.layers = one->layers;
    g_cull.groups = 0;
    for (uint32_t layer = 0; layer < one->layers; layer++) {
        g_cull.range_first[layer] = page
            [TF_LAYER_AT + TF_LAYER_WORDS * layer + TF_L_RANGE_FIRST];
    }
    g_cull.range_first[one->layers] = one->ranges;
    for (uint32_t layer = 0; layer < one->layers; layer++) {
        const uint32_t ranges = g_cull.range_first[layer + 1u] -
            g_cull.range_first[layer];
        const uint32_t groups = (ranges + group_ranges - 1u) / group_ranges;
        g_cull.group_first[layer] = g_cull.groups;
        g_cull.box_first[layer] = one->groups[layer];
        g_cull.groups += groups;
        if (4ull * DP_BOX_WORDS * ((uint64_t)one->groups[layer] + groups) > bytes) {
            return DP_BAD_NUMBERS;
        }
    }
    g_cull.group_first[one->layers] = g_cull.groups;
    for (uint32_t i = 0; i < DR_N_CAMERA_WORDS; i++) {
        __builtin_memcpy(&g_cull.camera[i], &view->camera[i], 4);
    }
    g_cull.width = (float)(32u * DP_GRID_ACROSS(view->grid));
    g_cull.height = (float)(32u * DP_GRID_DOWN(view->grid));
    g_cull.boxes = (const float*)DR_REGION(DP_REGION_GROUP_BOXES);
    g_cull.survivors = (uint32_t*)DR_REGION(DP_REGION_SURVIVORS);
    if (frame->bytes[DP_REGION_SURVIVORS] < 4ull * one->ranges) {
        return DP_SMALL_REGION;
    }
    *culled = 1;
    return dp_cull_test(&g_cull);
}

/* The work handler's command on the view's group, the page (its pull `kind`) its
 * block. 0, or DP_BAD_BLOCK. */
static uint32_t work_command(km_command_t* command, const view_t* view, uint32_t kind) {
    page_of()[TF_PULL] = kind;
    dr_flush(DP_REGION_PAGE, DP_REGION_PAGE_AT, PAGE_BYTES);
    DP_BUILD_WORK(command, 0, view->first, view->count);
    const int error = kmx_block(command, DP_REGION_PAGE, DP_REGION_PAGE_AT, PAGE_BYTES);
    return error == KMX_OK ? 0u : DP_BAD_BLOCK;
}

/* The sums on every core of the group. 0, or the code. */
static uint32_t sums(const view_t* one) {
    page_of()[TF_PULL] = 0;
    dr_flush(DP_REGION_PAGE, DP_REGION_PAGE_AT, PAGE_BYTES);
    km_command_t command;
    DP_BUILD_SUMS(&command, 0, one->first, one->count);
    if (kmx_block(&command, DP_REGION_PAGE, DP_REGION_PAGE_AT, PAGE_BYTES) != KMX_OK) {
        return DP_BAD_BLOCK;
    }
    kmx_progress(DP_WHERE_SUMS);
    return dr_run(&command);
}

/* From the slices' words (the sums', or the host's): each layer's place a slice (the
 * running sum of the slices' entries, its total kept in `one`) and the choice's
 * slices. 0, or the code. */
static uint32_t running(dr_frame_t* frame, view_t* one) {
    uint32_t code = 0;
    uint64_t mark = kmx_time();
    dp_choose_t* state = choose_of();
    if (dp_choose_reset(
            state,
            dr_number(frame, DP_N_POLICY),
            dr_number(frame, DP_N_NEAR),
            one->first,
            one->count,
            one->slices,
            one->slices_across
        )) {
        return DP_BAD_NUMBERS;
    }
    const uint32_t bytes = 4u * TS_WORDS * one->slices;
    dr_invalidate(DP_REGION_SLICES, DP_REGION_SLICES_AT, bytes);
    volatile uint32_t* words = (volatile uint32_t*)DR_REGION(DP_REGION_SLICES);
    /* volatile: no memset, which does not link */
    volatile uint32_t place[TR_LAYERS];
    for (uint32_t layer = 0; layer < TR_LAYERS; layer++) {
        place[layer] = 0;
    }
    uint32_t records = 0;
    for (uint32_t slice = 0; slice < one->slices; slice++) {
        volatile uint32_t* at = words + TS_WORDS * slice;
        if (at[TS_RECORDS] > TR_SLICE_RECORDS) {
            return DP_SLICE_FULL;
        }
        for (uint32_t layer = 0; layer < one->layers; layer++) {
            at[TS_PLACE(layer)] = place[layer];
            place[layer] += at[TS_ENTRIES(layer)];
        }
        dp_choose_slice(state, slice, at[TS_RECORDS], at[TS_WEIGHT]);
        records += at[TS_RECORDS];
    }
    for (uint32_t layer = 0; layer < one->layers; layer++) {
        one->entries[layer] = place[layer];
        if (place[layer] > one->list_slots[layer]) {
            code = DP_LISTS_SMALL;
        }
    }
    dr_flush(DP_REGION_SLICES, DP_REGION_SLICES_AT, bytes);
    frame->times[DP_R_TILE_THREADS] += records;
    frame->times[DP_T_RUNNING] += dr_ticks(&mark);
    return code;
}

/* The view's entries a layer into the need page (DP_N_NEED; none: nothing), copied by
 * the group's first core. DP_LISTS_SMALL, or DP_NEED_LATE. */
static uint32_t need_out(
    const dr_frame_t* frame, const dr_view_t* view, const view_t* one
) {
    const uint32_t to = dr_number(frame, DP_N_NEED);
    if (to == 0) {
        return DP_LISTS_SMALL;
    }
    volatile uint32_t* words = (volatile uint32_t*)DR_REGION(DP_REGION_NEED);
    for (uint32_t word = 0; word < DP_NEED_WORDS; word++) {
        words[word] = 0;
    }
    words[DP_NEED_VIEW] = view->index;
    words[DP_NEED_KIND] = view->kind;
    words[DP_NEED_CODE] = DP_LISTS_SMALL;
    for (uint32_t layer = 0; layer < one->layers; layer++) {
        words[DP_NEED_ENTRIES + one->rows[layer]] = one->entries[layer];
    }
    kmx_event event;
    const kmx_dram page = {to, KM_COPY_INTERLEAVED, DP_NEED_BYTES, 0u};
    const int status = kmx_store(
        DP_REGION_NEED,
        DP_REGION_NEED_AT,
        &page,
        DP_NEED_BYTES,
        one->first,
        1u,
        kmx_time() + DR_WAIT_TICKS,
        &event
    );
    return status == KMX_OK && event.kind == KM_EVENT_DONE ? DP_LISTS_SMALL
                                                           : DP_NEED_LATE;
}

/* The phases of the view (DP_N_PHASES; 0: every phase, or the tile alone for the
 * COLOUR view when DP_N_KEEP is set and the lists hold the eye's view). 0, or
 * DP_BAD_NUMBERS. */
static uint32_t phases_of(
    const dr_frame_t* frame, const dr_view_t* view, uint32_t* phases
) {
    *phases = dr_number(frame, DP_N_PHASES);
    if (*phases == 0) {
        const uint32_t kept = view->kind == DR_VIEW_COLOUR && g_eye_held &&
            dr_number(frame, DP_N_KEEP);
        *phases = kept ? DP_PHASE_TILE : DP_PHASE_ALL;
    }
    return *phases & ~DP_PHASE_ALL ? DP_BAD_NUMBERS : 0u;
}

uint32_t dp_view(dr_frame_t* frame, const dr_view_t* view) {
    uint64_t mark = kmx_time();
    view_t one;
    km_command_t command;
    uint32_t phases = 0;
    uint32_t code = phases_of(frame, view, &phases);
    if (view->kind != DR_VIEW_COLOUR || (phases & DP_PHASE_COUNT)) {
        g_eye_held = 0;
    }
    if (code == 0) {
        code = view_page(frame, view, &one);
    }
    if (code == 0 && (phases & DP_PHASE_COUNT)) {
        code = work_command(&command, &one, TP_COUNT);
    }
    uint32_t culled = 0;
    if (code == 0 && (phases & DP_PHASE_COUNT)) {
        code = cull_view(frame, view, &one, &culled);
    }
    if (code == 0 && (phases & DP_PHASE_COUNT)) {
        const kmx_pull counting = {
            one.ranges,
            1u,
            KMX_PULL_LOG,
            DP_REGION_LOG,
            culled ? dp_cull_pick : 0,
            (uint64_t)(uintptr_t)&g_cull,
            0
        };
        code = pull(&command, &counting, DP_WHERE_COUNT, DP_LATE_COUNT);
        frame->times[DP_R_RANGES] += one.ranges;
    }
    frame->times[DP_T_COUNT] += dr_ticks(&mark);
    if (code == 0 && (phases & DP_PHASE_SUMS)) {
        code = sums(&one);
    }
    if (code == 0 && (phases & (DP_PHASE_SUMS | DP_PHASE_PLACE | DP_PHASE_TILE))) {
        code = running(frame, &one);
    }
    if (code == DP_LISTS_SMALL) {
        code = need_out(frame, view, &one);
    }
    frame->times[DP_T_SUMS] += dr_ticks(&mark);
    if (code == 0 && (phases & DP_PHASE_PLACE)) {
        code = work_command(&command, &one, TP_PLACE);
    }
    if (code == 0 && (phases & DP_PHASE_PLACE)) {
        const kmx_pull placing = {
            one.ranges, 1u, KMX_PULL_REPLAY, DP_REGION_LOG, 0, 0, 0
        };
        code = pull(&command, &placing, DP_WHERE_PLACE, DP_LATE_PLACE);
    }
    frame->times[DP_T_PLACE] += dr_ticks(&mark);
    if (code == 0 && (phases & DP_PHASE_TILE)) {
        code = dp_frame_words(frame, view, (uint32_t*)page_of());
    }
    frame->times[DP_T_WORDS] += dr_ticks(&mark);
    if (code == 0 && (phases & DP_PHASE_TILE)) {
        code = work_command(&command, &one, TP_TILE);
    }
    if (code == 0 && (phases & DP_PHASE_TILE)) {
        dp_choose_t* state = choose_of();
        const kmx_pull tiles = {
            one.slices * TR_SLICE_RECORDS,
            1u,
            KMX_PULL_COUNT,
            0u,
            0,
            (uint64_t)(uintptr_t)state,
            dp_choose
        };
        code = pull(&command, &tiles, DP_WHERE_TILE, DP_LATE_TILE);
        frame->times[DP_R_NEAR_GIVEN] += state->near_given;
    }
    frame->times[DP_T_TILE] += dr_ticks(&mark);
    if (code != 0) {
        g_eye_held = 0;
    } else if (view->kind == DR_VIEW_COLOUR && phases == DP_PHASE_ALL) {
        g_eye_held = 1u;
    }
    return code;
}
