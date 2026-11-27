/* The sun's pass: the thread command SUN, a DEPTH view a quadrant of the shadow map run
 * through the director, each into its pages of the map; FIT, a fitted map's view;
 * LAMPS, lamp faces' views; their times a row each. */
#pragma once

#include <stdint.h>

#include "director.h"
#include "thread/depth_levels.h"

/* The sun region: LIGHT's table first, then from byte SHADOW_PCF_SUN_AT (a define: the
 * table's bytes) the sun's words below, then a camera a quadrant from
 * SHADOW_PCF_CAMERAS (DR_N_CAMERA_WORDS each) */
#define SHADOW_PCF_QUADRANTS 0u     /* the map's quadrants: a DEPTH view each */
#define SHADOW_PCF_ACROSS 1u        /* the quadrants a row of the map */
#define SHADOW_PCF_GRID 2u          /* a quadrant's grid word */
#define SHADOW_PCF_TILES 3u         /* its tiles */
#define SHADOW_PCF_TILES_ACROSS 4u  /* its tiles a row */
#define SHADOW_PCF_TILES_DOWN 5u    /* its rows of tiles */
#define SHADOW_PCF_TARGET 6u        /* the map's tensor */
#define SHADOW_PCF_TARGET_FIRST 7u  /* the map's first page in it */
#define SHADOW_PCF_TARGET_PAGES 8u  /* the tensor's pages */
#define SHADOW_PCF_MAPS_AT 9u       /* the page of maps' first byte in the region */
#define SHADOW_PCF_LEVELS_AT 10u    /* the levels' work bytes' first byte */
#define SHADOW_PCF_LEVELS_BYTES 11u /* their bytes */
#define SHADOW_PCF_CAMERAS 16u      /* the first quadrant's camera, on a line */

/* The times region: a row a SUN, FIT or LAMPS command (the last SHADOW_PCF_TIMES_ROWS),
 * its words the number, the code, the pass's ticks, the map (0 SUN's, 1 + the first
 * record's for FIT and LAMPS), the levels' ticks, their copies', the tiles ended here,
 * the command (SHADOW_PCF_COMMAND_*), then each view's */
#define SHADOW_PCF_TIMES_ROWS 64u
#define SHADOW_PCF_T_NUMBER 0u
#define SHADOW_PCF_T_CODE 1u
#define SHADOW_PCF_T_PASS 2u
#define SHADOW_PCF_T_MAP 3u
#define SHADOW_PCF_T_LEVELS 4u
#define SHADOW_PCF_T_COPIES 5u
#define SHADOW_PCF_T_ENDED 6u
#define SHADOW_PCF_T_COMMAND 7u
#define SHADOW_PCF_T_QUADRANT 8u
#define SHADOW_PCF_COMMAND_SUN 0u
#define SHADOW_PCF_COMMAND_FIT 1u
#define SHADOW_PCF_COMMAND_LAMPS 2u

/* The page of maps (in the sun region from SHADOW_PCF_MAPS_AT; the levels' work bytes
 * after it): the words below, then from SHADOW_PCF_M_RECORDS
 * two halves of SHADOW_PCF_M_MAPS records each (SHADOW_PCF_RECORD_WORDS a record, half
 * h's record k at SHADOW_PCF_M_RECORDS + (h * maps + k) * SHADOW_PCF_RECORD_WORDS) */
#define SHADOW_PCF_M_MAPS 0u      /* the records a half: whole, fits', faces' */
#define SHADOW_PCF_M_FIT_PAGES 1u /* the own maps' tensor's pages */
#define SHADOW_PCF_M_RECORDS 16u  /* the first record, on a line */

/* A record: a map's camera (DR_N_CAMERA_WORDS words, the block first), then */
#define SHADOW_PCF_R_TENSOR 16u        /* the tensor of its pages */
#define SHADOW_PCF_R_FIRST 17u         /* its first page there */
#define SHADOW_PCF_R_ACROSS 18u        /* its pages a row */
#define SHADOW_PCF_R_SIDE 19u          /* its width in texels (0: no map) */
#define SHADOW_PCF_R_TEXEL 20u         /* a texel's world size at the scene's centre */
#define SHADOW_PCF_R_BIAS 21u          /* its depth bias (float32) */
#define SHADOW_PCF_R_FILTER 22u        /* its filter (the lookup's) */
#define SHADOW_PCF_R_MARGIN 23u        /* the texels in from its edge a point needs */
#define SHADOW_PCF_R_LEVELS 24u        /* its levels below the map (0: none) */
#define SHADOW_PCF_R_LEVELS_TENSOR 25u /* the tensor of its tiles' levels' slots */
#define SHADOW_PCF_R_LEVELS_FIRST 26u  /* its first tile's slot there (and top) */
#define SHADOW_PCF_R_KIND 27u          /* SHADOW_PCF_KIND_* */
#define SHADOW_PCF_R_WHICH 28u         /* the cascade's index, the lamp's face */
#define SHADOW_PCF_R_VIEW 29u          /* the view that draws it */
#define SHADOW_PCF_R_TOPS 30u          /* the tensor of its tiles' tops */
#define SHADOW_PCF_R_COARSE_TENSOR 31u /* the tensor of its coarser levels */
#define SHADOW_PCF_R_COARSE_FIRST 32u  /* their first page there: a level a page */
#define SHADOW_PCF_R_DOWN 33u          /* its pages down */
#define SHADOW_PCF_R_GRID 34u          /* the grid word of the view that draws it */
#define SHADOW_PCF_R_TILES 35u         /* that view's tiles */
#define SHADOW_PCF_RECORD_WORDS 48u

#define SHADOW_PCF_KIND_WHOLE 0u /* the sun's map over the scene's box */
#define SHADOW_PCF_KIND_FIT 1u   /* a sun map fitted to a slice of the eye's view */
#define SHADOW_PCF_KIND_FACE 2u  /* a lamp's face */

/* A map's levels: those of a tile in its slot and its top (thread/depth_levels.h),
 * written by the DEPTH view's tiles; a tile drawn in bands ended here, then the tops
 * reduced to the levels coarser than a tile, each in a page of SHADOW_PCF_PAGE x
 * SHADOW_PCF_PAGE texels (row-major, from its corner) */
#define SHADOW_PCF_PAGE 32u

/* The unit's code: quadrants past the frame's views or its times row, or no tiles */
#define SHADOW_PCF_BAD_SUN (DR_UNIT_CODES + 1u)
/* FIT's: a map or a half out of the page of maps, a record with no map, a view out of
 * the frame's views, levels past the work region */
#define SHADOW_PCF_BAD_FIT (DR_UNIT_CODES + 2u)
/* a level's fetch or store did not finish */
#define SHADOW_PCF_COPY (DR_UNIT_CODES + 3u)
/* LAMPS's: a record out of the page of maps or not a face's, more faces than the times
 * row holds */
#define SHADOW_PCF_BAD_LAMPS (DR_UNIT_CODES + 4u)

/* SUN's words: a0 1 + the half of the page of maps the frames read after it (0: the
 * same) */
#define SHADOW_PCF_SUN_HALF 0u

/* FIT's words: a0 the map (its record's index), a1 the half its record is in, a2 1
 * when the frames read that half after it */
#define SHADOW_PCF_FIT_MAP 0u
#define SHADOW_PCF_FIT_HALF 1u
#define SHADOW_PCF_FIT_LAST 2u

/* LAMPS's words: a0 the first face's record, a1 the faces (records in turn) */
#define SHADOW_PCF_LAMPS_FIRST 0u
#define SHADOW_PCF_LAMPS_COUNT 1u

/* SUN: each quadrant's DEPTH view (its camera, the quadrant's grid, its pages of the
 * map as the target) by dr_view, in order; the whole map's levels when its record has
 * them; a times row of the director's (the units' parts, the code, the view and layer
 * that gave it) and one of its own; then the half its a0 names read. 0, or the first
 * code. */
uint32_t direct_shadow_pcf_unit_sun(dr_frame_t* frame, const km_command_t* command);

/* FIT: the record's map drawn by its DEPTH view into its pages, its levels when it has
 * them, a times row of its own (the quadrant word its view's); with a2 its half read by
 * the frames from then on. 0, or the first code. */
uint32_t direct_shadow_pcf_unit_fit(dr_frame_t* frame, const km_command_t* command);

/* LAMPS: each face's record from a0 (a1 of them) of the half the frames read drawn by
 * its DEPTH view into its pages, its levels when it has them; a times row of its own
 * (a view's word a face). 0, or the first code. */
uint32_t direct_shadow_pcf_unit_lamps(dr_frame_t* frame, const km_command_t* command);

/* The slot light.shadow_maps: 1 + the half of the page of maps the frames read. */
uint32_t direct_shadow_pcf_unit_shadow_maps(dr_frame_t* frame);
