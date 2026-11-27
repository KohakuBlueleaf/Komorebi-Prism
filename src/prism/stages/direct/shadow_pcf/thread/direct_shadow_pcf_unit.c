/* The sun's pass: the sun region's words, a DEPTH view a quadrant, the times row; the
 * page of maps: a fitted map's or a lamp face's DEPTH view, a map's levels, the half
 * the frames read. */
#include "direct_shadow_pcf_unit.h"

#define COPY_TICKS (4u * KMX_TICKS_PER_SECOND) /* a fetch's or a store's deadline */

/* SUN and FIT commands served, the half of the page of maps the frames read (in .data:
 * the image links no .bss) */
static uint32_t g_suns __attribute__((section(".data"))) = 0;
static uint32_t g_half __attribute__((section(".data"))) = 0;

/* The sun's words of the sun region (to the page of maps), read again from memory. */
static const volatile uint32_t* sun_words(void) {
    const uint32_t at = DR_DIRECT_SHADOW_PCF_REGION_SUN_AT + SHADOW_PCF_SUN_AT;
    dr_invalidate(DR_DIRECT_SHADOW_PCF_REGION_SUN, at, 64u);
    const volatile uint32_t* sun = (const volatile uint32_t*)dr_region(
        DR_DIRECT_SHADOW_PCF_REGION_SUN, at
    );
    const uint32_t end = sun[SHADOW_PCF_MAPS_AT];
    if (end > SHADOW_PCF_SUN_AT + 64u && end <= DR_DIRECT_SHADOW_PCF_REGION_SUN_BYTES) {
        dr_invalidate(DR_DIRECT_SHADOW_PCF_REGION_SUN, at, end - SHADOW_PCF_SUN_AT);
    }
    return sun;
}

/* Quadrant `quadrant`'s DEPTH view from the sun's words: view 1 + quadrant (the eye's
 * is 0), its camera and its address, the grid, its pages of the map. */
static void quadrant_view(
    const volatile uint32_t* sun, uint32_t quadrant, dr_view_t* view
) {
    const uint32_t camera = SHADOW_PCF_CAMERAS + quadrant * DR_N_CAMERA_WORDS;
    const uint32_t across = sun[SHADOW_PCF_ACROSS];
    view->index = 1 + quadrant;
    view->kind = DR_VIEW_DEPTH;
    for (uint32_t i = 0; i < DR_N_CAMERA_WORDS; i++) {
        view->camera[i] = sun[camera + i];
    }
    view->camera_at = DR_ADDRESS(DR_DIRECT_SHADOW_PCF_REGION_SUN) + SHADOW_PCF_SUN_AT +
        4u * camera;
    view->grid = sun[SHADOW_PCF_GRID];
    view->tiles = sun[SHADOW_PCF_TILES];
    view->target = sun[SHADOW_PCF_TARGET];
    view->target_across = across * sun[SHADOW_PCF_TILES_ACROSS];
    view->target_first = sun[SHADOW_PCF_TARGET_FIRST] +
        quadrant / across * sun[SHADOW_PCF_TILES_DOWN] * view->target_across +
        quadrant % across * sun[SHADOW_PCF_TILES_ACROSS];
    view->target_pages = sun[SHADOW_PCF_TARGET_PAGES];
}

/* A view's levels from `record` (none when it has none), `first` the map's first page.
 */
static void view_levels(
    const volatile uint32_t* record, uint32_t first, dr_view_t* view
) {
    const uint32_t levels = record[SHADOW_PCF_R_LEVELS];
    view->levels = levels ? record[SHADOW_PCF_R_LEVELS_TENSOR] : 0u;
    view->levels_shift = record[SHADOW_PCF_R_LEVELS_FIRST] - first;
    view->tops = levels ? record[SHADOW_PCF_R_TOPS] : 0u;
}

/* The levels' work bytes of the sun region: tops of `tiles` tiles, a slot, then the
 * coarse levels' pages; 0 when they pass the bytes the sun's words give. */
static uint32_t* levels_work(
    const volatile uint32_t* sun, uint32_t tiles, uint32_t coarse
) {
    const uint64_t bytes = (uint64_t)tiles * DEPTH_LEVELS_TOP_BYTES +
        DEPTH_LEVELS_SLOT_BYTES + 4ull * SHADOW_PCF_PAGE * SHADOW_PCF_PAGE * coarse;
    if (bytes > sun[SHADOW_PCF_LEVELS_BYTES] ||
        sun[SHADOW_PCF_LEVELS_AT] + sun[SHADOW_PCF_LEVELS_BYTES] >
            DR_DIRECT_SHADOW_PCF_REGION_SUN_BYTES) {
        return 0;
    }
    return (uint32_t*)dr_region(
        DR_DIRECT_SHADOW_PCF_REGION_SUN,
        DR_DIRECT_SHADOW_PCF_REGION_SUN_AT + sun[SHADOW_PCF_LEVELS_AT]
    );
}

/* A copy between the levels' work bytes (from byte `at`) and `pages` pages of
 * `page_bytes` of a tensor from page `first`: 0, or SHADOW_PCF_COPY. */
static uint32_t levels_copy(
    const dr_frame_t* frame,
    const volatile uint32_t* sun,
    uint32_t at,
    uint32_t tensor,
    uint32_t page_bytes,
    uint32_t first,
    uint32_t pages,
    int store
) {
    const kmx_dram dram = {tensor, KM_COPY_INTERLEAVED, page_bytes, first};
    const uint64_t offset = DR_DIRECT_SHADOW_PCF_REGION_SUN_AT +
        sun[SHADOW_PCF_LEVELS_AT] + at;
    const uint64_t bytes = (uint64_t)page_bytes * pages;
    kmx_event event;
    const int done = store ? kmx_store(
                                 DR_DIRECT_SHADOW_PCF_REGION_SUN,
                                 offset,
                                 &dram,
                                 bytes,
                                 0u,
                                 frame->cores,
                                 kmx_time() + COPY_TICKS,
                                 &event
                             )
                           : kmx_fetch(
                                 DR_DIRECT_SHADOW_PCF_REGION_SUN,
                                 offset,
                                 &dram,
                                 bytes,
                                 0u,
                                 frame->cores,
                                 kmx_time() + COPY_TICKS,
                                 &event
                             );
    return done == KMX_OK ? 0u : SHADOW_PCF_COPY;
}

/* The coarse levels' pages of a map of `across` x `down` tiles: one a level of the
 * tops' grid, each side halved (rounded up) down to 1 x 1. */
static uint32_t coarse_pages(uint32_t across, uint32_t down) {
    uint32_t pages = 0;
    while (across > 1u || down > 1u) {
        across = (across + 1u) / 2u;
        down = (down + 1u) / 2u;
        pages++;
    }
    return pages;
}

/* Before a map's views: its tiles' tops zeroed (no slot whole). 0, SHADOW_PCF_BAD_FIT
 * or SHADOW_PCF_COPY. */
static uint32_t levels_before(
    const dr_frame_t* frame,
    const volatile uint32_t* sun,
    const volatile uint32_t* record
) {
    const uint32_t across = record[SHADOW_PCF_R_ACROSS];
    const uint32_t tiles = across * record[SHADOW_PCF_R_DOWN];
    uint32_t* work = levels_work(
        sun, tiles, coarse_pages(across, record[SHADOW_PCF_R_DOWN])
    );
    if (work == 0 || tiles == 0) {
        return SHADOW_PCF_BAD_FIT;
    }
    for (uint32_t i = 0; i < tiles * DEPTH_LEVELS_TOP_BYTES / 4u; i++) {
        work[i] = 0;
    }
    return levels_copy(
        frame,
        sun,
        0u,
        record[SHADOW_PCF_R_TOPS],
        DEPTH_LEVELS_TOP_BYTES,
        record[SHADOW_PCF_R_LEVELS_FIRST],
        tiles,
        1
    );
}

/* After a map's views: each tile whose slot is not whole (drawn in bands) ended from
 * its 16 x 16, then the tops reduced to the coarse levels and stored. `copies` the
 * copies' ticks, `ended` the tiles ended. 0, SHADOW_PCF_BAD_FIT or SHADOW_PCF_COPY. */
static uint32_t levels_after(
    const dr_frame_t* frame,
    const volatile uint32_t* sun,
    const volatile uint32_t* record,
    uint32_t* copies,
    uint32_t* ended
) {
    const uint32_t across = record[SHADOW_PCF_R_ACROSS];
    const uint32_t down = record[SHADOW_PCF_R_DOWN];
    const uint32_t tiles = across * down;
    const uint32_t coarse = coarse_pages(across, down);
    uint32_t* work = levels_work(sun, tiles, coarse);
    if (work == 0 || tiles == 0) {
        return SHADOW_PCF_BAD_FIT;
    }
    const uint32_t slots = record[SHADOW_PCF_R_LEVELS_TENSOR];
    const uint32_t first = record[SHADOW_PCF_R_LEVELS_FIRST];
    const uint32_t tops = DEPTH_LEVELS_TOP_BYTES / 4u;
    const uint32_t slot_at = tiles * DEPTH_LEVELS_TOP_BYTES;
    uint32_t* slot = work + slot_at / 4u;
    uint64_t mark = kmx_time();
    uint32_t code = levels_copy(
        frame,
        sun,
        0u,
        record[SHADOW_PCF_R_TOPS],
        DEPTH_LEVELS_TOP_BYTES,
        first,
        tiles,
        0
    );
    for (uint32_t t = 0; code == 0 && t < tiles; t++) {
        uint32_t* top = work + t * tops;
        if (top[DEPTH_LEVELS_TOP_WHOLE] == 1u) {
            continue;
        }
        code = levels_copy(
            frame, sun, slot_at, slots, DEPTH_LEVELS_SLOT_BYTES, first + t, 1u, 0
        );
        if (code == 0) {
            depth_levels_below(slot);
            top[DEPTH_LEVELS_TOP_VALUE] = slot[DEPTH_LEVELS_L5];
            code = levels_copy(
                frame, sun, slot_at, slots, DEPTH_LEVELS_SLOT_BYTES, first + t, 1u, 1
            );
        }
        (*ended)++;
    }
    *copies += (uint32_t)(kmx_time() - mark);
    const uint32_t page_words = SHADOW_PCF_PAGE * SHADOW_PCF_PAGE;
    const uint32_t coarse_at = slot_at + DEPTH_LEVELS_SLOT_BYTES;
    uint32_t* pages = work + coarse_at / 4u;
    const uint32_t* from = work;
    uint32_t stride = tops * across, step = tops;
    uint32_t ga = across, gd = down;
    for (uint32_t level = 0; code == 0 && level < coarse; level++) {
        const uint32_t ha = (ga + 1u) / 2u, hd = (gd + 1u) / 2u;
        uint32_t* to = pages + level * page_words;
        for (uint32_t y = 0; y < hd; y++) {
            for (uint32_t x = 0; x < ha; x++) {
                uint32_t most = 0;
                for (uint32_t dy = 0; dy < 2u && 2u * y + dy < gd; dy++) {
                    for (uint32_t dx = 0; dx < 2u && 2u * x + dx < ga; dx++) {
                        most = depth_levels_most(
                            most, from[(2u * y + dy) * stride + (2u * x + dx) * step]
                        );
                    }
                }
                to[y * SHADOW_PCF_PAGE + x] = most;
            }
        }
        from = to;
        stride = SHADOW_PCF_PAGE;
        step = 1u;
        ga = ha;
        gd = hd;
    }
    if (code == 0 && coarse) {
        mark = kmx_time();
        code = levels_copy(
            frame,
            sun,
            coarse_at,
            record[SHADOW_PCF_R_COARSE_TENSOR],
            4u * page_words,
            record[SHADOW_PCF_R_COARSE_FIRST],
            coarse,
            1
        );
        *copies += (uint32_t)(kmx_time() - mark);
    }
    return code;
}

/* The page of maps' words (the sun's words `sun`), read again from memory; 0 when the
 * sun's words do not place it in the region. */
static const volatile uint32_t* maps_words(const volatile uint32_t* sun) {
    const uint32_t at = sun[SHADOW_PCF_MAPS_AT];
    const uint32_t end = sun[SHADOW_PCF_LEVELS_AT];
    if (at < SHADOW_PCF_SUN_AT || end <= at ||
        end > DR_DIRECT_SHADOW_PCF_REGION_SUN_BYTES) {
        return 0;
    }
    dr_invalidate(
        DR_DIRECT_SHADOW_PCF_REGION_SUN,
        DR_DIRECT_SHADOW_PCF_REGION_SUN_AT + at,
        end - at
    );
    return (const volatile uint32_t*)dr_region(
        DR_DIRECT_SHADOW_PCF_REGION_SUN, DR_DIRECT_SHADOW_PCF_REGION_SUN_AT + at
    );
}

/* Half `half`'s record `map` of the page of maps `maps` (of `bytes`), or 0 when out of
 * it. */
static const volatile uint32_t* record_of(
    const volatile uint32_t* maps, uint32_t bytes, uint32_t half, uint32_t map
) {
    if (maps == 0) {
        return 0;
    }
    const uint32_t count = maps[SHADOW_PCF_M_MAPS];
    const uint32_t at = SHADOW_PCF_M_RECORDS +
        (half * count + map) * SHADOW_PCF_RECORD_WORDS;
    if (half > 1u || map >= count || 4u * (at + SHADOW_PCF_RECORD_WORDS) > bytes) {
        return 0;
    }
    return maps + at;
}

/* A times row of the times region begun for the command numbered g_suns: its words
 * a row and its byte in the region. */
static uint32_t* times_row(uint32_t* words, uint32_t* at) {
    *words = DR_DIRECT_SHADOW_PCF_REGION_SUN_TIMES_BYTES / 4u / SHADOW_PCF_TIMES_ROWS;
    *at = DR_DIRECT_SHADOW_PCF_REGION_SUN_TIMES_AT +
        4u * *words * (g_suns % SHADOW_PCF_TIMES_ROWS);
    uint32_t* row = (uint32_t*)dr_region(DR_DIRECT_SHADOW_PCF_REGION_SUN_TIMES, *at);
    for (uint32_t i = 0; i < *words; i++) {
        row[i] = 0;
    }
    return row;
}

/* The times row at byte `at` ended (`words` words) and written back, the command
 * counted. */
static void times_end(
    uint32_t* row, uint32_t words, uint32_t at, uint32_t code, uint64_t started
) {
    row[SHADOW_PCF_T_NUMBER] = g_suns;
    row[SHADOW_PCF_T_CODE] = code;
    row[SHADOW_PCF_T_PASS] = (uint32_t)(kmx_time() - started);
    dr_flush(DR_DIRECT_SHADOW_PCF_REGION_SUN_TIMES, at, 4u * words);
    g_suns++;
}

uint32_t direct_shadow_pcf_unit_sun(dr_frame_t* frame, const km_command_t* command) {
    uint32_t code = dr_ready(frame);
    const uint64_t started = dr_row_start(frame);
    uint64_t mark = started;
    uint32_t row_words, at;
    uint32_t* row = times_row(&row_words, &at);
    const volatile uint32_t* sun = sun_words();
    const uint32_t quadrants = sun[SHADOW_PCF_QUADRANTS];
    const uint32_t across = sun[SHADOW_PCF_ACROSS];
    const uint32_t half = command->a0 ? command->a0 - 1u : g_half;
    row[SHADOW_PCF_T_COMMAND] = SHADOW_PCF_COMMAND_SUN;
    if (code == 0 &&
        (quadrants == 0 || quadrants >= DR_VIEWS || across == 0 ||
         across * across != quadrants || sun[SHADOW_PCF_TILES] == 0 ||
         SHADOW_PCF_T_QUADRANT + quadrants > row_words || half > 1u)) {
        code = SHADOW_PCF_BAD_SUN;
    }
    const uint32_t bytes = sun[SHADOW_PCF_LEVELS_AT] - sun[SHADOW_PCF_MAPS_AT];
    const volatile uint32_t* whole = record_of(maps_words(sun), bytes, half, 0u);
    if (code == 0 && whole == 0) {
        code = SHADOW_PCF_BAD_SUN;
    }
    if (code == 0) {
        dr_invalidate(
            DR_REGION_LAYERS,
            4u * DR_LAYER_WORDS * DR_LAYERS,
            4u * DR_LAYER_WORDS * DR_LAYERS * quadrants
        );
        if (whole[SHADOW_PCF_R_LEVELS]) {
            code = levels_before(frame, sun, whole);
            row[SHADOW_PCF_T_LEVELS] = dr_ticks(&mark);
        }
    }
    for (uint32_t quadrant = 0; code == 0 && quadrant < quadrants; quadrant++) {
        dr_view_t view;
        quadrant_view(sun, quadrant, &view);
        view_levels(whole, sun[SHADOW_PCF_TARGET_FIRST], &view);
        code = dr_view(frame, &view);
        row[SHADOW_PCF_T_QUADRANT + quadrant] = dr_ticks(&mark);
    }
    if (code == 0 && whole[SHADOW_PCF_R_LEVELS]) {
        code = levels_after(
            frame, sun, whole, &row[SHADOW_PCF_T_COPIES], &row[SHADOW_PCF_T_ENDED]
        );
        row[SHADOW_PCF_T_LEVELS] += dr_ticks(&mark);
    }
    if (code == 0) {
        g_half = half;
    }
    times_end(row, row_words, at, code, started);
    return dr_row_end(frame, code, started);
}

/* Record `record`'s DEPTH view: its view index and camera (the page of maps' words at
 * byte `camera_at` of the region), its view's grid and tiles, its pages. */
static void fit_view(
    const volatile uint32_t* maps,
    const volatile uint32_t* record,
    uint32_t camera_at,
    dr_view_t* view
) {
    view->index = record[SHADOW_PCF_R_VIEW];
    view->kind = DR_VIEW_DEPTH;
    for (uint32_t i = 0; i < DR_N_CAMERA_WORDS; i++) {
        view->camera[i] = record[i];
    }
    view->camera_at = DR_ADDRESS(DR_DIRECT_SHADOW_PCF_REGION_SUN) + camera_at;
    view->grid = record[SHADOW_PCF_R_GRID];
    view->tiles = record[SHADOW_PCF_R_TILES];
    view->target = record[SHADOW_PCF_R_TENSOR];
    view->target_first = record[SHADOW_PCF_R_FIRST];
    view->target_across = record[SHADOW_PCF_R_ACROSS];
    view->target_pages = maps[SHADOW_PCF_M_FIT_PAGES];
}

/* Record `record` of the page of maps `maps` (of kind `kind`) drawn: its levels'
 * tops zeroed, its DEPTH view (its ticks in `row`'s view word `slot`), its levels
 * ended. 0, `bad` for a record that is not one, or the first code. */
static uint32_t record_drawn(
    dr_frame_t* frame,
    const volatile uint32_t* sun,
    const volatile uint32_t* maps,
    const volatile uint32_t* record,
    uint32_t kind,
    uint32_t bad,
    uint32_t* row,
    uint32_t slot,
    uint64_t* mark
) {
    if (record == 0 || record[SHADOW_PCF_R_KIND] != kind ||
        record[SHADOW_PCF_R_SIDE] == 0 || record[SHADOW_PCF_R_VIEW] == 0 ||
        record[SHADOW_PCF_R_VIEW] >= DR_VIEWS || record[SHADOW_PCF_R_TILES] == 0) {
        return bad;
    }
    dr_invalidate(
        DR_REGION_LAYERS,
        4u * DR_LAYER_WORDS * DR_LAYERS * record[SHADOW_PCF_R_VIEW],
        4u * DR_LAYER_WORDS * DR_LAYERS
    );
    dr_view_t view;
    const uint32_t camera_at = sun[SHADOW_PCF_MAPS_AT] +
        (uint32_t)((const volatile uint8_t*)record - (const volatile uint8_t*)maps);
    fit_view(maps, record, camera_at, &view);
    view_levels(record, record[SHADOW_PCF_R_FIRST], &view);
    uint32_t code = 0;
    if (record[SHADOW_PCF_R_LEVELS]) {
        code = levels_before(frame, sun, record);
        row[SHADOW_PCF_T_LEVELS] += dr_ticks(mark);
    }
    if (code == 0) {
        code = dr_view(frame, &view);
        row[SHADOW_PCF_T_QUADRANT + slot] = dr_ticks(mark);
    }
    if (code == 0 && record[SHADOW_PCF_R_LEVELS]) {
        code = levels_after(
            frame, sun, record, &row[SHADOW_PCF_T_COPIES], &row[SHADOW_PCF_T_ENDED]
        );
        row[SHADOW_PCF_T_LEVELS] += dr_ticks(mark);
    }
    return code;
}

uint32_t direct_shadow_pcf_unit_fit(dr_frame_t* frame, const km_command_t* command) {
    uint32_t code = dr_ready(frame);
    const uint64_t started = dr_row_start(frame);
    uint64_t mark = started;
    uint32_t row_words, at;
    uint32_t* row = times_row(&row_words, &at);
    const uint32_t map = command->a0;
    const uint32_t half = command->a1;
    const volatile uint32_t* sun = sun_words();
    const volatile uint32_t* maps = maps_words(sun);
    const uint32_t bytes = sun[SHADOW_PCF_LEVELS_AT] - sun[SHADOW_PCF_MAPS_AT];
    row[SHADOW_PCF_T_MAP] = 1u + map;
    row[SHADOW_PCF_T_COMMAND] = SHADOW_PCF_COMMAND_FIT;
    if (code == 0 && SHADOW_PCF_T_QUADRANT + 1u > row_words) {
        code = SHADOW_PCF_BAD_FIT;
    }
    if (code == 0) {
        code = record_drawn(
            frame,
            sun,
            maps,
            record_of(maps, bytes, half, map),
            SHADOW_PCF_KIND_FIT,
            SHADOW_PCF_BAD_FIT,
            row,
            0u,
            &mark
        );
    }
    if (code == 0 && command->a2) {
        g_half = half;
    }
    times_end(row, row_words, at, code, started);
    return dr_row_end(frame, code, started);
}

uint32_t direct_shadow_pcf_unit_lamps(dr_frame_t* frame, const km_command_t* command) {
    uint32_t code = dr_ready(frame);
    const uint64_t started = dr_row_start(frame);
    uint64_t mark = started;
    uint32_t row_words, at;
    uint32_t* row = times_row(&row_words, &at);
    const uint32_t first = command->a0;
    const uint32_t faces = command->a1;
    const volatile uint32_t* sun = sun_words();
    const volatile uint32_t* maps = maps_words(sun);
    const uint32_t bytes = sun[SHADOW_PCF_LEVELS_AT] - sun[SHADOW_PCF_MAPS_AT];
    row[SHADOW_PCF_T_MAP] = 1u + first;
    row[SHADOW_PCF_T_COMMAND] = SHADOW_PCF_COMMAND_LAMPS;
    if (code == 0 && (faces == 0 || SHADOW_PCF_T_QUADRANT + faces > row_words)) {
        code = SHADOW_PCF_BAD_LAMPS;
    }
    for (uint32_t face = 0; code == 0 && face < faces; face++) {
        code = record_drawn(
            frame,
            sun,
            maps,
            record_of(maps, bytes, g_half, first + face),
            SHADOW_PCF_KIND_FACE,
            SHADOW_PCF_BAD_LAMPS,
            row,
            face,
            &mark
        );
    }
    times_end(row, row_words, at, code, started);
    return dr_row_end(frame, code, started);
}

uint32_t direct_shadow_pcf_unit_shadow_maps(dr_frame_t* frame) {
    (void)frame;
    return 1u + g_half;
}
