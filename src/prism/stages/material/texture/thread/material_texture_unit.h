/* The texture stage's thread unit: a layer's SHADE on the cores, its words the layer's
 * columns, built by its class's builder (DR_MATERIAL_TEXTURE_BUILD). */
#pragma once

#include <stdint.h>

#include "director.h"

/* SHADE of a layer, waited for. A COLOUR view: every layer with a directory, lit (the
 * view's camera, the layer's surface) when its surface column is set, else unlit. A
 * DEPTH view: the merging layer's lit merge (mode 0) of the view's own directory and
 * lists into its opaque layer's, as the sun's pass needs; nothing for the opaque layer
 * or without a surface. 0, or the code. */
uint32_t material_texture_unit_layer(
    dr_frame_t* frame, const dr_view_t* view, const dr_layer_t* layer
);
