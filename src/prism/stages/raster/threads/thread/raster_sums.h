/* The sums' results on the frame's thread: the slices' words the sums wrote, read
 * back; each layer's running sum over the slices into their places (TS_PLACE). */
#pragma once

#include <stdint.h>

#include "../../../../core/include/thread/record.h"

/* raster_sums_place's code: a layer's lists hold fewer slots than its slices'
 * entries (the layer is the code less RASTER_SUMS_PAST) */
#define RASTER_SUMS_PAST 0x100u

#ifdef __cplusplus
extern "C" {
#endif

/* What a view's slices hold over all of them */
typedef struct {
    uint32_t records;            /* tile threads */
    uint64_t weight;             /* their weight */
    uint32_t entries[TR_LAYERS]; /* each layer's list slots used */
} raster_sums_t;

/* The `count` slices' words at `slices` (TS_WORDS each, read back after the sums):
 * each of `layers` layers' places as the running sum of the slices' entries in slice
 * order, written to their TS_PLACE words, and the view's totals into `totals`. 0, or
 * RASTER_SUMS_PAST + the first layer past its `list_slots`; the places are written
 * either way. */
uint32_t raster_sums_place(
    volatile uint32_t* slices,
    uint32_t count,
    uint32_t layers,
    const uint32_t* list_slots,
    raster_sums_t* totals
);

#ifdef __cplusplus
}
#endif
