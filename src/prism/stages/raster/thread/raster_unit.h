/* The raster stage's thread unit: a layer of a view is COUNT, SUM, the tiles to cut,
 * HIST, HSUM, the middle pass, PLACE, SETUP, FILL, each submitted to the cores (its
 * places and the RASTER_K_* numbers: the generated header and the build's defines). */
#pragma once

#include <stdint.h>

#include "director.h"
#include "raster_middle.h"

/* The unit's codes: more tiles than the capacity; past the heavy tables; the middle
 * pass could not lay the lists out; fewer list slots than the frame needs; the work
 * region under its struct */
#define RASTER_BAD_GRID (DR_UNIT_CODES + 1u)
#define RASTER_TOO_MANY_HEAVY (DR_UNIT_CODES + 2u)
#define RASTER_NO_LAYOUT (DR_UNIT_CODES + 3u)
#define RASTER_LISTS_SMALL (DR_UNIT_CODES + 4u)
#define RASTER_SMALL_REGION (DR_UNIT_CODES + 5u)

/* The areas of the camera region: one a (view, layer) */
#define RASTER_AREAS (DR_VIEWS * DR_LAYERS)

/* The work region: the middle pass's arrays, the heavy tiles and their bands, each
 * area's blocks a core and whether its costs and next ranges are in */
typedef struct {
    rm_scratch scratch;
    uint32_t heavy[RM_MAX_HEAVY], bands[RM_MAX_HEAVY];
    uint32_t ranges[RASTER_AREAS][RM_MAX_CORES + 1];
    uint32_t cuts[RM_MAX_CORES + 1];
    uint32_t ranged[RASTER_AREAS], ready[RASTER_AREAS];
} raster_work_t;

/* Once: the work region checked, the regions' stale lines written back, the empty
 * tile's planes loaded. 0, or the code. */
uint32_t raster_unit_setup(dr_frame_t* frame);

/* A layer of a view, COUNT to FILL (or as far as the number `steps`); SETUP the
 * shaded one when the layer's column `shade` names its shade blocks. 0, or the code. */
uint32_t raster_unit_layer(
    dr_frame_t* frame, const dr_view_t* view, const dr_layer_t* layer
);

/* raster_ranges.c: the view's page of the area `area` (its first page): the camera
 * and the grid word. */
void raster_view_page(const dr_view_t* view, uint32_t area);

/* raster_ranges.c: each core's blocks of the layer's mesh for COUNT and SETUP into the
 * area's pages: the even partition, then by the last frame's costs: 0, or
 * DR_PARALLEL. */
uint32_t raster_ranges(
    const dr_frame_t* frame,
    raster_work_t* work,
    const dr_layer_t* layer,
    uint32_t area_index,
    uint32_t area
);
