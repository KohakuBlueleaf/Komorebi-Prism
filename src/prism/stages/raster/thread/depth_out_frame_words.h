/* The depth_out step's words of a DEPTH view's frame's page: the target's first page,
 * its pages a row of tiles, its pages (PRISM_TF_DEPTH_OUT_*), and the target as the
 * page's target (TF_TARGET). */
#pragma once

#include <stdint.h>

#include "director.h"

/* A DEPTH view's depth_out words into `page` (a COLOUR view: none). 0, or the code. */
uint32_t depth_out_frame_words(
    dr_frame_t* frame, const dr_view_t* view, uint32_t* page
);
