/* The material step's words of the frame's page, from the texture unit's layer rows. */
#include "material_frame_words.h"

#include "../../../../../core/include/thread/record.h"
#include "../kernels/material_words.h"

/* The view's row of its layer `layer`. */
static const volatile uint32_t* layer_row(const dr_view_t* view, uint32_t layer) {
    return (const volatile uint32_t*)dr_region(
        DR_REGION_LAYERS, 4u * DR_LAYER_WORDS * (view->index * DR_LAYERS + layer)
    );
}

/* The step's words of `view` at the places `at` (layers, textures, table). */
static uint32_t frame_words(
    dr_frame_t* frame, const dr_view_t* view, uint32_t* page, const uint32_t at[3]
) {
    uint32_t layers = 0, textures = 0, table = 0;
    for (uint32_t layer = 0; layer < frame->layers && layer < TR_LAYERS; layer++) {
        const volatile uint32_t* row = layer_row(view, layer);
        if (view->kind == DR_VIEW_DEPTH && !row[DR_L_DEPTH]) {
            continue;
        }
        if (row[DR_MATERIAL_TEXTURE_L_SHADE_DIRECTORY] == 0) {
            continue;
        }
        const uint32_t mode = row[DR_MATERIAL_TEXTURE_L_MODE];
        if (mode > MATERIAL_MODE_MOST) {
            return DR_BAD_ARGS;
        }
        const uint32_t bits = MATERIAL_SHADED |
            (row[DR_MATERIAL_TEXTURE_L_OPAQUE] != 0 ? MATERIAL_MERGING : 0u) |
            mode << MATERIAL_MODE_SHIFT;
        layers |= bits << (MATERIAL_LAYER_BITS * layer);
        textures = row[DR_MATERIAL_TEXTURE_L_TEXTURES];
        table = row[DR_MATERIAL_TEXTURE_L_SHADE_TABLE];
    }
    page[at[0]] = layers;
    page[at[1]] = textures;
    page[at[2]] = table;
    return 0;
}

#ifdef PRISM_TF_MATERIAL_LAYERS
uint32_t material_frame_words(
    dr_frame_t* frame, const dr_view_t* view, uint32_t* page
) {
    static const uint32_t at[3] = {
        PRISM_TF_MATERIAL_LAYERS, PRISM_TF_MATERIAL_TEXTURES, PRISM_TF_MATERIAL_TABLE
    };
    return frame_words(frame, view, page, at);
}
#endif

#ifdef PRISM_TF_MATERIAL_LIT_LAYERS
uint32_t material_lit_frame_words(
    dr_frame_t* frame, const dr_view_t* view, uint32_t* page
) {
    static const uint32_t at[3] = {
        PRISM_TF_MATERIAL_LIT_LAYERS,
        PRISM_TF_MATERIAL_LIT_TEXTURES,
        PRISM_TF_MATERIAL_LIT_TABLE
    };
    return frame_words(frame, view, page, at);
}
#endif
