/* The direct light's thread unit: a COLOUR view's LIGHT after every layer's SHADE, in
 * the displayed form, or with a glass layer the linear form then the glass form; its
 * words its numbers and the columns it takes, built by its class's builder
 * (DR_DIRECT_LIGHT_BUILD). The forms are the build's defines (DIRECT_LIGHT_*); with
 * DIRECT_LIGHT_SHOWN the view's last LIGHT carries it. */
#pragma once

#include <stdint.h>

#include "director.h"

/* LIGHT of a COLOUR view (a DEPTH view has none), each waited for. 0, or the code. */
uint32_t direct_light_unit_frame(dr_frame_t* frame, const dr_view_t* view);
