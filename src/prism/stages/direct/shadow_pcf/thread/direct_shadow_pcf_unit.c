/* The sun's pass: the sun region's words, a DEPTH view a quadrant, the times row. */
#include "direct_shadow_pcf_unit.h"

/* SUN commands served (in .data: the image links no .bss) */
static uint32_t g_suns __attribute__((section(".data"))) = 0;

/* The sun's words of the sun region, read again from memory. */
static const volatile uint32_t* sun_words(void) {
    dr_invalidate(
        DR_DIRECT_SHADOW_PCF_REGION_SUN,
        DR_DIRECT_SHADOW_PCF_REGION_SUN_AT + SHADOW_PCF_SUN_AT,
        DR_DIRECT_SHADOW_PCF_REGION_SUN_BYTES - SHADOW_PCF_SUN_AT
    );
    return (const volatile uint32_t*)dr_region(
        DR_DIRECT_SHADOW_PCF_REGION_SUN,
        DR_DIRECT_SHADOW_PCF_REGION_SUN_AT + SHADOW_PCF_SUN_AT
    );
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

uint32_t direct_shadow_pcf_unit_sun(dr_frame_t* frame, const km_command_t* command) {
    (void)command;
    uint32_t code = dr_ready(frame);
    const uint64_t started = dr_row_start(frame);
    uint64_t mark = started;
    const uint32_t row_words = DR_DIRECT_SHADOW_PCF_REGION_SUN_TIMES_BYTES / 4u /
        SHADOW_PCF_TIMES_ROWS;
    const uint32_t at = 4u * row_words * (g_suns % SHADOW_PCF_TIMES_ROWS);
    uint32_t* row = (uint32_t*)dr_region(
        DR_DIRECT_SHADOW_PCF_REGION_SUN_TIMES,
        DR_DIRECT_SHADOW_PCF_REGION_SUN_TIMES_AT + at
    );
    for (uint32_t i = 0; i < row_words; i++) {
        row[i] = 0;
    }
    const volatile uint32_t* sun = sun_words();
    const uint32_t quadrants = sun[SHADOW_PCF_QUADRANTS];
    const uint32_t across = sun[SHADOW_PCF_ACROSS];
    if (code == 0 &&
        (quadrants == 0 || quadrants >= DR_VIEWS || across == 0 ||
         across * across != quadrants || sun[SHADOW_PCF_TILES] == 0 ||
         SHADOW_PCF_T_QUADRANT + quadrants > row_words)) {
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
    row[SHADOW_PCF_T_NUMBER] = g_suns;
    row[SHADOW_PCF_T_CODE] = code;
    row[SHADOW_PCF_T_PASS] = (uint32_t)(kmx_time() - started);
    dr_flush(
        DR_DIRECT_SHADOW_PCF_REGION_SUN_TIMES,
        DR_DIRECT_SHADOW_PCF_REGION_SUN_TIMES_AT + at,
        4u * row_words
    );
    g_suns++;
    return dr_row_end(frame, code, started);
}
