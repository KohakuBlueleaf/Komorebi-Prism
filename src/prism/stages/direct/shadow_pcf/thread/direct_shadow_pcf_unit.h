/* The sun's pass: the thread command SUN, a DEPTH view a quadrant of the shadow map run
 * through the director, each into its pages of the map; its times a row of its own. */
#pragma once

#include <stdint.h>

#include "director.h"

/* The sun region: LIGHT's table first, then from byte SHADOW_PCF_SUN_AT (a define: the
 * table's bytes) the sun's words below, then a camera a quadrant from
 * SHADOW_PCF_CAMERAS (DR_N_CAMERA_WORDS each) */
#define SHADOW_PCF_QUADRANTS 0u    /* the map's quadrants: a DEPTH view each */
#define SHADOW_PCF_ACROSS 1u       /* the quadrants a row of the map */
#define SHADOW_PCF_GRID 2u         /* a quadrant's grid word */
#define SHADOW_PCF_TILES 3u        /* its tiles */
#define SHADOW_PCF_TILES_ACROSS 4u /* its tiles a row */
#define SHADOW_PCF_TILES_DOWN 5u   /* its rows of tiles */
#define SHADOW_PCF_TARGET 6u       /* the map's tensor */
#define SHADOW_PCF_TARGET_FIRST 7u /* the map's first page in it */
#define SHADOW_PCF_TARGET_PAGES 8u /* the tensor's pages */
#define SHADOW_PCF_CAMERAS 16u     /* the first quadrant's camera, on a line */

/* The times region: a row a SUN command (the last SHADOW_PCF_TIMES_ROWS), its words
 * the number, the code, the pass's ticks, then each quadrant's */
#define SHADOW_PCF_TIMES_ROWS 64u
#define SHADOW_PCF_T_NUMBER 0u
#define SHADOW_PCF_T_CODE 1u
#define SHADOW_PCF_T_PASS 2u
#define SHADOW_PCF_T_QUADRANT 3u

/* The unit's code: quadrants past the frame's views or its times row, or no tiles */
#define SHADOW_PCF_BAD_SUN (DR_UNIT_CODES + 1u)

/* SUN: each quadrant's DEPTH view (its camera, the quadrant's grid, its pages of the
 * map as the target) by dr_view, in order; a times row of the director's (the units'
 * parts, the code, the view and layer that gave it) and one of its own. 0, or the
 * first code. */
uint32_t direct_shadow_pcf_unit_sun(dr_frame_t* frame, const km_command_t* command);
