/* The near tile step's words of a view's frame's page: the light pages' tensor and
 * whether they hold the standing camera's (PRISM_TF_NEAR_TILE_*). */
#pragma once

#include <stdint.h>

#include "director.h"

/* A COLOUR view's near tile words into `page` (a DEPTH view: none). 0, or the code. */
uint32_t near_tile_frame_words(
    dr_frame_t* frame, const dr_view_t* view, uint32_t* page
);
