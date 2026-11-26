/* The material step's words of the frame's page, a view (material_words.h). */
#pragma once

#include <stdint.h>

#include "director.h"

/* Writes the material step's words of `view` into `page` (the unlit step's places, or
 * the lit one's): each layer's bits from its row of the texture unit's columns (a DEPTH
 * view: the layers it draws), the textures' and the table's tensors. 0, or DR_BAD_ARGS
 * for a mode past the word's bits. */
uint32_t material_frame_words(
    dr_frame_t* frame, const dr_view_t* view, uint32_t* page
);
uint32_t material_lit_frame_words(
    dr_frame_t* frame, const dr_view_t* view, uint32_t* page
);
