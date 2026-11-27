/* The sun's pass: the sun region's words, a DEPTH view a quadrant, the times row; the
 * page of maps: a fitted map's DEPTH view, a map's levels, the half the frames read. */
#include "direct_shadow_pcf_unit.h"

#define COPY_TICKS (4u * KMX_TICKS_PER_SECOND) /* a fetch's or a store's deadline */

/* SUN and FIT commands served, the half of the page of maps the frames read (in .data:
 * the image links no .bss) */
static uint32_t g_suns __attribute__((section(".data"))) = 0;
static uint32_t g_half __attribute__((section(".data"))) = 0;

/* A level's reduction on the four cores: from level `from` (side `side`, its pages
 * `across` a row) to `to` (side / 2), `rows` rows of `to` from row `row` */
typedef struct {
    const uint32_t* from;
    uint32_t* to;
    uint32_t side, row, rows, from_across, to_across, to_column;
} level_t;

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

/* Texel (x, y)'s word in pages of SHADOW_PCF_PAGE, `across` pages a row. */
static inline uint32_t texel_at(uint32_t x, uint32_t y, uint32_t across) {
    const uint32_t page = (y / SHADOW_PCF_PAGE) * across + x / SHADOW_PCF_PAGE;
    return page * SHADOW_PCF_PAGE * SHADOW_PCF_PAGE +
        (y % SHADOW_PCF_PAGE) * SHADOW_PCF_PAGE + x % SHADOW_PCF_PAGE;
}

/* A level's pages a row for its side. */
static inline uint32_t level_across(uint32_t side) {
    return side > SHADOW_PCF_PAGE ? side / SHADOW_PCF_PAGE : 1u;
}

/* The largest of four 1/z (none negative: their bits order as the values). */
static inline uint32_t most_of(uint32_t a, uint32_t b, uint32_t c, uint32_t d) {
    const uint32_t ab = a > b ? a : b;
    const uint32_t cd = c > d ? c : d;
    return ab > cd ? ab : cd;
}

/* A level under a page a side (level_t), texel by texel, on core 0. */
static void small_level(const level_t* level) {
    const uint32_t half = level->side / 2u;
    const uint32_t a = level->from_across;
    for (uint32_t y = 0; y < level->rows; y++) {
        for (uint32_t x = 0; x < half; x++) {
            const uint32_t* f = level->from;
            level
                ->to[texel_at(level->to_column + x, level->row + y, level->to_across)] =
                most_of(
                    f[texel_at(2u * x, 2u * y, a)],
                    f[texel_at(2u * x + 1u, 2u * y, a)],
                    f[texel_at(2u * x, 2u * y + 1u, a)],
                    f[texel_at(2u * x + 1u, 2u * y + 1u, a)]
                );
        }
    }
}

/* Core `core`'s quarter of a level's reduction (level_t): an output page from the 2 x 2
 * pages above it, row by row. */
static void level_part(int core, void* arg) {
    const level_t* level = (const level_t*)arg;
    const uint32_t page = SHADOW_PCF_PAGE * SHADOW_PCF_PAGE;
    const uint32_t pages = level->side / 2u / SHADOW_PCF_PAGE;
    if (pages == 0) {
        if (core == 0) {
            small_level(level);
        }
        return;
    }
    const uint32_t count = pages * pages;
    const uint32_t row = level->row / SHADOW_PCF_PAGE;
    const uint32_t column = level->to_column / SHADOW_PCF_PAGE;
    for (
        uint32_t p = count * (uint32_t)core / 4u;
        p < count * ((uint32_t)core + 1u) / 4u;
        p++
    ) {
        const uint32_t py = p / pages, px = p % pages;
        uint32_t* out = level->to +
            ((row + py) * level->to_across + column + px) * page;
        const uint32_t* above = level->from +
            (2u * py * level->from_across + 2u * px) * page;
        for (uint32_t r = 0; r < SHADOW_PCF_PAGE; r++) {
            const uint32_t* left = above +
                (r < SHADOW_PCF_PAGE / 2u ? 0u : level->from_across * page) +
                (2u * r % SHADOW_PCF_PAGE) * SHADOW_PCF_PAGE;
            const uint32_t* right = left + page;
            uint32_t* o = out + r * SHADOW_PCF_PAGE;
            for (uint32_t c = 0; c < SHADOW_PCF_PAGE / 2u; c++) {
                o[c] = most_of(
                    left[2u * c],
                    left[2u * c + 1u],
                    left[SHADOW_PCF_PAGE + 2u * c],
                    left[SHADOW_PCF_PAGE + 2u * c + 1u]
                );
                o[SHADOW_PCF_PAGE / 2u + c] = most_of(
                    right[2u * c],
                    right[2u * c + 1u],
                    right[SHADOW_PCF_PAGE + 2u * c],
                    right[SHADOW_PCF_PAGE + 2u * c + 1u]
                );
            }
        }
    }
}

/* The pages of every level of a map of side `side` (SHADOW_PCF_PAGE x SHADOW_PCF_PAGE
 * texels a page). */
static uint32_t levels_pages(uint32_t side) {
    uint32_t pages = 0;
    for (uint32_t s = side / 2u; s >= 1u; s /= 2u) {
        pages += level_across(s) * level_across(s);
    }
    return pages;
}

/* The map of `record` reduced into its levels: in pieces of SHADOW_PCF_PIECE_PAGES
 * pages a side fetched into the levels region, each piece's first level into the levels
 * region after the piece, the rest from the first, then every level stored. 0,
 * SHADOW_PCF_BAD_FIT, DR_PARALLEL or SHADOW_PCF_COPY. */
static uint32_t map_levels(
    const dr_frame_t* frame,
    const volatile uint32_t* sun,
    const volatile uint32_t* record,
    uint32_t* copies
) {
    const uint32_t side = record[SHADOW_PCF_R_SIDE];
    const uint32_t across = record[SHADOW_PCF_R_ACROSS];
    const uint32_t piece_side = SHADOW_PCF_PIECE_PAGES * SHADOW_PCF_PAGE;
    const uint32_t pieces = side > piece_side ? side / piece_side : 1u;
    const uint32_t piece_pages = side > piece_side ? SHADOW_PCF_PIECE_PAGES : across;
    const uint64_t page_bytes = 4u * SHADOW_PCF_PAGE * SHADOW_PCF_PAGE;
    const uint64_t piece_bytes = page_bytes * piece_pages * piece_pages;
    const uint64_t out_bytes = page_bytes * levels_pages(side);
    if (side < 2u || side % SHADOW_PCF_PAGE || across * SHADOW_PCF_PAGE != side ||
        piece_bytes + out_bytes > sun[SHADOW_PCF_LEVELS_BYTES] ||
        sun[SHADOW_PCF_LEVELS_AT] + sun[SHADOW_PCF_LEVELS_BYTES] >
            DR_DIRECT_SHADOW_PCF_REGION_SUN_BYTES ||
        record[SHADOW_PCF_R_LEVELS] == 0) {
        return SHADOW_PCF_BAD_FIT;
    }
    const uint32_t work = DR_DIRECT_SHADOW_PCF_REGION_SUN_AT +
        sun[SHADOW_PCF_LEVELS_AT];
    uint32_t* piece = (uint32_t*)dr_region(DR_DIRECT_SHADOW_PCF_REGION_SUN, work);
    uint32_t* out = piece + piece_bytes / 4u;
    /* a piece's rows of pages one fetch when they are the map's whole rows */
    const uint32_t rows = piece_pages == across ? 1u : piece_pages;
    const uint32_t fetched = piece_pages * piece_pages / rows;
    for (uint32_t py = 0; py < pieces; py++) {
        for (uint32_t px = 0; px < pieces; px++) {
            uint64_t mark = kmx_time();
            for (uint32_t r = 0; r < rows; r++) {
                const uint32_t first = (py * piece_pages + r) * across +
                    px * piece_pages;
                const kmx_dram from = {
                    record[SHADOW_PCF_R_TENSOR],
                    KM_COPY_INTERLEAVED,
                    (uint32_t)page_bytes,
                    record[SHADOW_PCF_R_FIRST] + first
                };
                kmx_event event;
                if (kmx_fetch(
                        DR_DIRECT_SHADOW_PCF_REGION_SUN,
                        work + page_bytes * fetched * r,
                        &from,
                        page_bytes * fetched,
                        0u,
                        frame->cores,
                        kmx_time() + COPY_TICKS,
                        &event
                    ) != KMX_OK) {
                    return SHADOW_PCF_COPY;
                }
            }
            *copies += (uint32_t)(kmx_time() - mark);
            const uint32_t half = piece_pages * SHADOW_PCF_PAGE / 2u;
            level_t level = {
                piece,
                out,
                2u * half,
                py * half,
                half,
                piece_pages,
                level_across(side / 2u),
                px * half
            };
            if (dr_parallel(level_part, &level)) {
                return DR_PARALLEL;
            }
        }
    }
    uint32_t* from = out;
    for (uint32_t s = side / 2u; s >= 2u; s /= 2u) {
        uint32_t* to = from +
            level_across(s) * level_across(s) * SHADOW_PCF_PAGE * SHADOW_PCF_PAGE;
        level_t level = {
            from, to, s, 0u, s / 2u, level_across(s), level_across(s / 2u), 0u
        };
        if (dr_parallel(level_part, &level)) {
            return DR_PARALLEL;
        }
        from = to;
    }
    const kmx_dram to = {
        record[SHADOW_PCF_R_LEVELS_TENSOR],
        KM_COPY_INTERLEAVED,
        (uint32_t)page_bytes,
        record[SHADOW_PCF_R_LEVELS_FIRST]
    };
    kmx_event event;
    const uint64_t mark = kmx_time();
    if (kmx_store(
            DR_DIRECT_SHADOW_PCF_REGION_SUN,
            work + piece_bytes,
            &to,
            out_bytes,
            0u,
            frame->cores,
            kmx_time() + COPY_TICKS,
            &event
        ) != KMX_OK) {
        return SHADOW_PCF_COPY;
    }
    *copies += (uint32_t)(kmx_time() - mark);
    return 0;
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
    if (code == 0 &&
        (quadrants == 0 || quadrants >= DR_VIEWS || across == 0 ||
         across * across != quadrants || sun[SHADOW_PCF_TILES] == 0 ||
         SHADOW_PCF_T_QUADRANT + quadrants > row_words || half > 1u)) {
        code = SHADOW_PCF_BAD_SUN;
    }
    if (code == 0) {
        dr_invalidate(
            DR_REGION_LAYERS,
            4u * DR_LAYER_WORDS * DR_LAYERS,
            4u * DR_LAYER_WORDS * DR_LAYERS * quadrants
        );
    }
    for (uint32_t quadrant = 0; code == 0 && quadrant < quadrants; quadrant++) {
        dr_view_t view;
        quadrant_view(sun, quadrant, &view);
        code = dr_view(frame, &view);
        row[SHADOW_PCF_T_QUADRANT + quadrant] = dr_ticks(&mark);
    }
    if (code == 0) {
        const uint32_t bytes = sun[SHADOW_PCF_LEVELS_AT] - sun[SHADOW_PCF_MAPS_AT];
        const volatile uint32_t* whole = record_of(maps_words(sun), bytes, half, 0u);
        if (whole == 0) {
            code = SHADOW_PCF_BAD_SUN;
        } else if (whole[SHADOW_PCF_R_LEVELS]) {
            code = map_levels(frame, sun, whole, &row[SHADOW_PCF_T_COPIES]);
            row[SHADOW_PCF_T_LEVELS] = dr_ticks(&mark);
        }
    }
    if (code == 0) {
        g_half = half;
    }
    times_end(row, row_words, at, code, started);
    return dr_row_end(frame, code, started);
}

/* Record `record`'s DEPTH view: its view index and camera (the page of maps' words at
 * byte `camera_at` of the region), a fitted view's grid and tiles, its pages. */
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
    view->grid = maps[SHADOW_PCF_M_GRID];
    view->tiles = maps[SHADOW_PCF_M_TILES];
    view->target = record[SHADOW_PCF_R_TENSOR];
    view->target_first = record[SHADOW_PCF_R_FIRST];
    view->target_across = record[SHADOW_PCF_R_ACROSS];
    view->target_pages = maps[SHADOW_PCF_M_FIT_PAGES];
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
    const volatile uint32_t* record = record_of(maps, bytes, half, map);
    row[SHADOW_PCF_T_MAP] = 1u + map;
    if (code == 0 &&
        (record == 0 || record[SHADOW_PCF_R_KIND] != SHADOW_PCF_KIND_FIT ||
         record[SHADOW_PCF_R_SIDE] == 0 || record[SHADOW_PCF_R_VIEW] == 0 ||
         record[SHADOW_PCF_R_VIEW] >= DR_VIEWS || maps[SHADOW_PCF_M_TILES] == 0 ||
         SHADOW_PCF_T_QUADRANT + 1u > row_words)) {
        code = SHADOW_PCF_BAD_FIT;
    }
    if (code == 0) {
        dr_invalidate(
            DR_REGION_LAYERS,
            4u * DR_LAYER_WORDS * DR_LAYERS * record[SHADOW_PCF_R_VIEW],
            4u * DR_LAYER_WORDS * DR_LAYERS
        );
        dr_view_t view;
        const uint32_t camera_at = sun[SHADOW_PCF_MAPS_AT] +
            (uint32_t)((const volatile uint8_t*)record - (const volatile uint8_t*)maps);
        fit_view(maps, record, camera_at, &view);
        code = dr_view(frame, &view);
        row[SHADOW_PCF_T_QUADRANT] = dr_ticks(&mark);
    }
    if (code == 0 && record[SHADOW_PCF_R_LEVELS]) {
        code = map_levels(frame, sun, record, &row[SHADOW_PCF_T_COPIES]);
        row[SHADOW_PCF_T_LEVELS] = dr_ticks(&mark);
    }
    if (code == 0 && command->a2) {
        g_half = half;
    }
    times_end(row, row_words, at, code, started);
    return dr_row_end(frame, code, started);
}

uint32_t direct_shadow_pcf_unit_shadow_maps(dr_frame_t* frame) {
    (void)frame;
    return 1u + g_half;
}
