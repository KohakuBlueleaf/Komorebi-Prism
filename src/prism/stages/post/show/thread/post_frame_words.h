/* The post step's words of a view's frame's page: the thresholds' table, the display's
 * pages (PRISM_TF_POST_*), and the display as the page's target (TF_TARGET). */
#pragma once

#include <stdint.h>

#include "director.h"

/* A COLOUR view's post words into `page` (a DEPTH view: none). 0, or the code. */
uint32_t post_frame_words(dr_frame_t* frame, const dr_view_t* view, uint32_t* page);
