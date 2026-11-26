/* The direct light's unit: LIGHT's words from its numbers, the view and the columns it
 * takes (the frame's directories, SHADE's table, LIGHT's table), its times. */
#include "direct_light_unit.h"

/* The bit the last LIGHT of a COLOUR view carries: with the option light_shows, its
 * mover B converts for display (no SHOW after it). */
#if defined(DIRECT_LIGHT_SHOWN)
#define DIRECT_LIGHT_LAST DIRECT_LIGHT_SHOWN
#else
#define DIRECT_LIGHT_LAST 0u
#endif

/* The row of the view's layer `layer` (its index in the view). */
static const volatile uint32_t* layer_row(const dr_view_t* view, uint32_t layer) {
    return (const volatile uint32_t*)dr_region(
        DR_REGION_LAYERS, 4u * DR_LAYER_WORDS * (view->index * DR_LAYERS + layer)
    );
}

/* LIGHT in `form` over the frame of the view's first layer: the surface's directory
 * `surface`, the glass layer's directory `glass` and SHADE's table `shade_table` (the
 * glass form's; else the surface and 0). */
static uint32_t light(
    dr_frame_t* frame,
    const dr_view_t* view,
    uint32_t form,
    uint32_t surface,
    uint32_t glass,
    uint32_t shade_table
) {
    const volatile uint32_t* first = layer_row(view, 0);
    km_command_t command;
    DR_DIRECT_LIGHT_BUILD(light)(
        &command,
        0,
        0,
        frame->workers,
        first[DR_DIRECT_LIGHT_TAKES_LIGHT_SHADOW_MAP_SUN_TABLE],
        shade_table,
        view->camera_at,
        frame->bank_plus_one | view->grid,
        form
    );
    dr_word(
        &command,
        DR_PLACE(LIGHT_DIRECTORY),
        first[DR_DIRECT_LIGHT_TAKES_FRAME_VISIBILITY_DIRECTORY]
    );
    dr_word(&command, DR_PLACE(LIGHT_GLASS), glass);
    dr_word(&command, DR_PLACE(LIGHT_SURFACE), surface);
    return dr_run(&command);
}

uint32_t direct_light_unit_frame(dr_frame_t* frame, const dr_view_t* view) {
    if (view->kind == DR_VIEW_DEPTH) {
        return 0;
    }
    uint64_t mark = kmx_time();
    const uint32_t surface = dr_number(frame, DR_DIRECT_LIGHT_N_LIGHT_SURFACE);
    const uint32_t glass_layer = dr_number(frame, DR_DIRECT_LIGHT_N_LIGHT_GLASS);
    if (glass_layer > frame->layers) {
        return DR_BAD_ARGS;
    }
    uint32_t code = light(
        frame,
        view,
        glass_layer ? DIRECT_LIGHT_LINEAR : DIRECT_LIGHT_DISPLAYED | DIRECT_LIGHT_LAST,
        surface,
        surface,
        0
    );
    frame->times[DR_DIRECT_LIGHT_T_LIGHT] = dr_ticks(&mark);
    if (code || !glass_layer) {
        return code;
    }
    const volatile uint32_t* glass = layer_row(view, glass_layer - 1);
    code = light(
        frame,
        view,
        DIRECT_LIGHT_GLASS | DIRECT_LIGHT_LAST,
        dr_number(frame, DR_DIRECT_LIGHT_N_LIGHT_GLASS_SURFACE),
        glass[DR_DIRECT_LIGHT_TAKES_FRAME_VISIBILITY_DIRECTORY],
        glass[DR_DIRECT_LIGHT_TAKES_MESH_ATTRIBUTES_SHADE_TABLE]
    );
    frame->times[DR_DIRECT_LIGHT_T_LIGHT_GLASS] = dr_ticks(&mark);
    return code;
}
