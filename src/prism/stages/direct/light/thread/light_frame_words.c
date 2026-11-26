/* The light step's words of a view's frame's page, from the light thread unit's
 * numbers, the column it takes and, with the job thread, the field's version its slots
 * give. */
#include "light_frame_words.h"

/* The row of the view's layer `layer` (its index in the view). */
static const volatile uint32_t* layer_row(const dr_view_t* view, uint32_t layer) {
    return (const volatile uint32_t*)dr_region(
        DR_REGION_LAYERS, 4u * DR_LAYER_WORDS * (view->index * DR_LAYERS + layer)
    );
}

/* A float's bits. */
__attribute__((unused)) static uint32_t bits_of(float value) {
    union {
        float f;
        uint32_t u;
    } both = {value};

    return both.u;
}

/* The field's version words (none: 0): its first page for its half, a channel's unit
 * (1 / max code)^2 x the scale (light model field.field_words), the scale. */
static void field_words(dr_frame_t* frame, uint32_t* page) {
    page[PRISM_TF_LIGHT_FIELD_FIRST] = 0;
#if defined(DIRECT_LIGHT_FIELD_BY_SLOT)
    const uint32_t given = DR_GIVE_LIGHT_FIELD(frame); /* 1 + the half, 0: none yet */
    if (given == 0) {
        return;
    }
    const uint32_t scale_bits = DR_GIVE_LIGHT_FIELD_SCALE(frame);

    union {
        uint32_t u;
        float f;
    } scale = {scale_bits};

    const uint32_t bits[3] = {
        DIRECT_LIGHT_FIELD_BITS_R, DIRECT_LIGHT_FIELD_BITS_G, DIRECT_LIGHT_FIELD_BITS_B
    };
    for (uint32_t channel = 0; channel < 3; channel++) {
        const float unit = 1.0f / (float)((1u << bits[channel]) - 1u);
        page[PRISM_TF_LIGHT_FIELD_UNIT_R + channel] = bits_of((unit * unit) * scale.f);
    }
    page[PRISM_TF_LIGHT_FIELD_SCALE] = scale_bits;
    page[PRISM_TF_LIGHT_FIELD_FIRST] = dr_number(
                                           frame, DR_DIRECT_LIGHT_N_LIGHT_FIELD_FIRST
                                       ) +
        (given - 1u) * dr_number(frame, DR_DIRECT_LIGHT_N_LIGHT_FIELD_PAGES);
#else
    (void)frame;
#endif
}

uint32_t light_frame_words(dr_frame_t* frame, const dr_view_t* view, uint32_t* page) {
    if (view->kind == DR_VIEW_DEPTH) {
        return 0;
    }
    const uint32_t glass = dr_number(frame, DR_DIRECT_LIGHT_N_LIGHT_GLASS);
    if (glass > frame->layers) {
        return DR_BAD_ARGS;
    }
    page[PRISM_TF_LIGHT_TABLE] = layer_row(
        view, 0
    )[DR_DIRECT_LIGHT_TAKES_LIGHT_SHADOW_MAP_SUN_TABLE];
    page[PRISM_TF_LIGHT_PAGES] = dr_number(frame, DR_DIRECT_LIGHT_N_LIGHT_PAGES);
    page[PRISM_TF_LIGHT_GLASS] = glass;
    field_words(frame, page);
    if (page[PRISM_TF_LIGHT_TABLE] == 0 || page[PRISM_TF_LIGHT_PAGES] == 0) {
        return DR_BAD_ARGS;
    }
    return 0;
}
