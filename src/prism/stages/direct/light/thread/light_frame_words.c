/* The light step's words of a view's frame's page, from the light unit's numbers and
 * the columns it takes. */
#include "light_frame_words.h"

/* The row of the view's layer `layer` (its index in the view). */
static const volatile uint32_t* layer_row(const dr_view_t* view, uint32_t layer) {
    return (const volatile uint32_t*)dr_region(
        DR_REGION_LAYERS, 4u * DR_LAYER_WORDS * (view->index * DR_LAYERS + layer)
    );
}

uint32_t light_frame_words(dr_frame_t* frame, const dr_view_t* view, uint32_t* page) {
    if (view->kind == DR_VIEW_DEPTH) {
        return 0;
    }
    const uint32_t glass = dr_number(frame, DR_DIRECT_LIGHT_N_LIGHT_GLASS);
    if (glass > frame->layers) {
        return DR_BAD_ARGS;
    }
    const volatile uint32_t* first = layer_row(view, 0);
    page[PRISM_TF_LIGHT_TABLE] = first
        [DR_DIRECT_LIGHT_TAKES_LIGHT_SHADOW_MAP_SUN_TABLE];
    page[PRISM_TF_LIGHT_PAGES] = dr_number(frame, DR_DIRECT_LIGHT_N_LIGHT_PAGES);
    page[PRISM_TF_LIGHT_GLASS] = glass;
    page[PRISM_TF_LIGHT_SHADE_TABLE] = glass
        ? layer_row(view, glass - 1)[DR_DIRECT_LIGHT_TAKES_MESH_ATTRIBUTES_SHADE_TABLE]
        : 0;
    if (page[PRISM_TF_LIGHT_TABLE] == 0 || page[PRISM_TF_LIGHT_PAGES] == 0) {
        return DR_BAD_ARGS;
    }
    return 0;
}
