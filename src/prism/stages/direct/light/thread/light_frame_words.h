/* The light step's words of a view's frame's page: LIGHT's table, the light pages, the
 * glass layer's SHADE table and 1 + its index (PRISM_TF_LIGHT_*). */
#pragma once

#include <stdint.h>

#include "director.h"

/* A COLOUR view's light words into `page` (a DEPTH view: none). 0, or the code. */
uint32_t light_frame_words(dr_frame_t* frame, const dr_view_t* view, uint32_t* page);
