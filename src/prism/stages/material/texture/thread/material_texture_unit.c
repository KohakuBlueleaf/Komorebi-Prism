/* The texture unit: a layer's SHADE from its columns, its time the layer's. */
#include "material_texture_unit.h"

#define FIRST_LAYER 0u /* the opaque layer's row in a view */

/* The view's row of its layer `layer`. */
static const volatile uint32_t* layer_row(const dr_view_t* view, uint32_t layer) {
    return (const volatile uint32_t*)dr_region(
        DR_REGION_LAYERS, 4u * DR_LAYER_WORDS * (view->index * DR_LAYERS + layer)
    );
}

/* SHADE of `layer` with these words (the camera 0: an unlit form, `surface` any
 * tensor), waited for, its time the layer's. 0, or the code. */
static uint32_t shade(
    dr_frame_t* frame,
    const dr_view_t* view,
    const dr_layer_t* layer,
    uint32_t directory,
    uint32_t lists,
    uint32_t opaque,
    uint32_t mode,
    uint32_t camera,
    uint32_t surface
) {
    uint64_t mark = kmx_time();
    km_command_t command;
    DR_MATERIAL_TEXTURE_BUILD(shade)(
        &command,
        0,
        0,
        frame->workers,
        opaque,
        mode,
        camera ? frame->bank_plus_one | view->grid : view->grid,
        camera
    );
    dr_word(&command, DR_PLACE(SHADE_DIRECTORY), directory);
    dr_word(&command, DR_PLACE(SHADE_LISTS), lists);
    dr_word(
        &command, DR_PLACE(SHADE_TEXTURES), layer->words[DR_MATERIAL_TEXTURE_L_TEXTURES]
    );
    dr_word(
        &command, DR_PLACE(SHADE_TABLE), layer->words[DR_MATERIAL_TEXTURE_L_SHADE_TABLE]
    );
    dr_word(
        &command,
        DR_PLACE(SHADE_PROFILE),
        layer->words[DR_MATERIAL_TEXTURE_L_SHADE_PROFILE]
    );
    dr_word(&command, DR_PLACE(SHADE_SURFACE), surface);
    const uint32_t code = dr_run(&command);
    *dr_layer_time(frame, layer, DR_MATERIAL_TEXTURE_T_SHADE) += dr_ticks(&mark);
    return code;
}

/* A DEPTH view's layer: the merging layer's 1/z into the opaque layer's of the view's
 * own directories (the lit form, mode 0); the glass layer's T over the opaque layer's
 * (its depth mode, kShadeTransmit) when the view keeps T. */
static uint32_t depth_layer(
    dr_frame_t* frame, const dr_view_t* view, const dr_layer_t* layer
) {
    const uint32_t surface = layer->words[DR_MATERIAL_TEXTURE_L_SHADE_SURFACE];
    const uint32_t depth_mode = layer->words[DR_MATERIAL_TEXTURE_L_DEPTH_MODE];
    const volatile uint32_t* first = layer_row(view, FIRST_LAYER);
    if (depth_mode != 0) {
        if (view->transmit == 0 || surface == 0) {
            return 0;
        }
        return shade(
            frame,
            view,
            layer,
            layer->words[DR_MATERIAL_TEXTURE_TAKES_FRAME_LISTS_DIRECTORY],
            layer->words[DR_MATERIAL_TEXTURE_TAKES_FRAME_LISTS_LISTS],
            first[DR_MATERIAL_TEXTURE_TAKES_FRAME_LISTS_DIRECTORY],
            depth_mode,
            view->camera_at,
            surface
        );
    }
    if (layer->words[DR_MATERIAL_TEXTURE_L_OPAQUE] == 0 || surface == 0) {
        return 0;
    }
    return shade(
        frame,
        view,
        layer,
        layer->words[DR_MATERIAL_TEXTURE_TAKES_FRAME_LISTS_DIRECTORY],
        layer->words[DR_MATERIAL_TEXTURE_TAKES_FRAME_LISTS_LISTS],
        first[DR_MATERIAL_TEXTURE_TAKES_FRAME_LISTS_DIRECTORY],
        0u,
        view->camera_at,
        surface
    );
}

uint32_t material_texture_unit_layer(
    dr_frame_t* frame, const dr_view_t* view, const dr_layer_t* layer
) {
    const uint32_t directory = layer->words[DR_MATERIAL_TEXTURE_L_SHADE_DIRECTORY];
    if (directory == 0) {
        return 0;
    }
    if (view->kind == DR_VIEW_DEPTH) {
        return depth_layer(frame, view, layer);
    }
    const uint32_t surface = layer->words[DR_MATERIAL_TEXTURE_L_SHADE_SURFACE];
    return shade(
        frame,
        view,
        layer,
        directory,
        layer->words[DR_MATERIAL_TEXTURE_L_SHADE_LISTS],
        layer->words[DR_MATERIAL_TEXTURE_L_OPAQUE],
        layer->words[DR_MATERIAL_TEXTURE_L_MODE],
        surface ? view->camera_at : 0u,
        surface ? surface : directory /* unlit: any tensor */
    );
}
