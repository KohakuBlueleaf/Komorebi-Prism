/* The sums' results on the frame's thread: the slices' places and the view's totals. */
#include "raster_sums.h"

uint32_t raster_sums_place(
    volatile uint32_t* slices,
    uint32_t count,
    uint32_t layers,
    const uint32_t* list_slots,
    raster_sums_t* totals
) {
    uint32_t code = 0;
    totals->records = 0;
    totals->weight = 0;
    for (uint32_t s = 0; s < count; s++) {
        totals->records += slices[TS_WORDS * s + TS_RECORDS];
        totals->weight += slices[TS_WORDS * s + TS_WEIGHT];
    }
    for (uint32_t layer = 0; layer < TR_LAYERS; layer++) {
        uint64_t place = 0;
        for (uint32_t s = 0; s < count && layer < layers; s++) {
            volatile uint32_t* words = slices + TS_WORDS * s;
            words[TS_PLACE(layer)] = (uint32_t)place;
            place += words[TS_ENTRIES(layer)];
        }
        totals->entries[layer] = (uint32_t)place;
        if (layer < layers && place > list_slots[layer] && code == 0) {
            code = RASTER_SUMS_PAST + layer;
        }
    }
    return code;
}
