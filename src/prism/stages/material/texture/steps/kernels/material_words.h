/* The material step's words of the frame's page (the unlit step's
 * PRISM_TF_MATERIAL_*, the lit one's PRISM_TF_MATERIAL_LIT_*), read by the kernels and
 * written on the frame's thread: LAYERS holds MATERIAL_LAYER_BITS a layer (layer 0 in
 * the lowest), TEXTURES the texture pages' tensor, TABLE SHADE's table tensor. */
#pragma once

#include <stdint.h>

#define MATERIAL_LAYER_BITS 8u
#define MATERIAL_SHADED 1u     /* the layer is shaded (its SHADE directory is set) */
#define MATERIAL_MERGING 2u    /* it merges into the opaque layer (opaque word set) */
#define MATERIAL_MODE_SHIFT 2u /* its kShade* bits above these two */
#define MATERIAL_MODE_MOST 63u /* the largest kShade* bits the word holds */

/* Layer `layer`'s bits in the word `layers` */
#define MATERIAL_LAYER(layers, layer) \
    (((layers) >> (MATERIAL_LAYER_BITS * (layer))) & ((1u << MATERIAL_LAYER_BITS) - 1u))
