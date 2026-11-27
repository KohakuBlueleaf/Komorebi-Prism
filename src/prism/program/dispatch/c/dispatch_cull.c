/* The count ranges a view walks (dispatch_cull.h). */
#include "dispatch_cull.h"

/* cull.SLACK: the box's margin, of the camera-space magnitudes it is made from */
#define DP_BOX_SLACK 1e-5f

static inline float magnitude(float value) {
    return value < 0.0f ? -value : value;
}

/* The most of a times a value in [low, high] */
static inline float most_of(float a, float low, float high) {
    return a >= 0.0f ? a * high : a * low;
}

uint32_t dp_box_outside(
    const float* camera, const float* box, float width, float height
) {
    float size[3], d[3];
    for (uint32_t i = 0; i < 3u; i++) {
        const float centre = (box[i] + box[3u + i]) * 0.5f;
        size[i] = (box[3u + i] - box[i]) * 0.5f;
        d[i] = centre - camera[i];
    }
    float scale = (magnitude(d[0]) + magnitude(d[1])) + magnitude(d[2]);
    scale = scale + ((size[0] + size[1]) + size[2]);
    float low[3], high[3];
    for (uint32_t row = 0; row < 3u; row++) {
        const float* r = camera + 3u + 3u * row;
        const float at = (d[0] * r[0] + d[1] * r[1]) + d[2] * r[2];
        float reach = (size[0] * magnitude(r[0]) + size[1] * magnitude(r[1])) +
            size[2] * magnitude(r[2]);
        reach = reach + scale * DP_BOX_SLACK;
        low[row] = at - reach;
        high[row] = at + reach;
    }
    const float focal = camera[12], cx = camera[13], cy = camera[14];
    if (high[2] < camera[15]) {
        return 1u;
    }
    if (focal * high[0] + most_of(cx, low[2], high[2]) < 0.0f) {
        return 1u;
    }
    if (-focal * low[0] + most_of(width - cx, low[2], high[2]) < 0.0f) {
        return 1u;
    }
    if (most_of(cy, low[2], high[2]) - focal * low[1] < 0.0f) {
        return 1u;
    }
    return focal * high[1] + most_of(height - cy, low[2], high[2]) < 0.0f;
}

/* The layer of the view's group `group` */
static uint32_t layer_of(const dp_cull_t* cull, uint32_t group) {
    uint32_t layer = 0;
    while (group >= cull->group_first[layer + 1u]) {
        layer++;
    }
    return layer;
}

/* The first range of the view's group `group` */
static uint32_t range_of(const dp_cull_t* cull, uint32_t group) {
    if (group >= cull->groups) {
        return cull->ranges;
    }
    const uint32_t layer = layer_of(cull, group);
    return cull->range_first[layer] +
        (group - cull->group_first[layer]) * cull->group_ranges;
}

/* Core `core`'s share: its groups tested, the ranges of those not cut written from the
 * first range of its first group on */
static void test_part(int core, void* arg) {
    dp_cull_t* cull = (dp_cull_t*)arg;
    const uint32_t first = cull->part_group[core], end = cull->part_group[core + 1];
    const uint32_t at = cull->part_range[core];
    uint32_t kept = 0;
    for (uint32_t group = first; group < end; group++) {
        const uint32_t layer = layer_of(cull, group);
        const uint32_t own = group - cull->group_first[layer];
        const float* box = cull->boxes + DP_BOX_WORDS * (cull->box_first[layer] + own);
        if (dp_box_outside(cull->camera, box, cull->width, cull->height)) {
            continue;
        }
        const uint32_t from = cull->range_first[layer] + own * cull->group_ranges;
        const uint32_t layer_end = cull->range_first[layer + 1u];
        const uint32_t to = from + cull->group_ranges < layer_end
            ? from + cull->group_ranges
            : layer_end;
        for (uint32_t range = from; range < to; range++) {
            cull->survivors[at + kept++] = range;
        }
    }
    cull->part_kept[core] = kept;
}

uint32_t dp_cull_test(dp_cull_t* cull) {
    for (uint32_t part = 0; part <= DP_CULL_PARTS; part++) {
        cull->part_group[part] = (uint32_t)((uint64_t)cull->groups * part /
                                            DP_CULL_PARTS);
    }
    for (uint32_t part = 0; part < DP_CULL_PARTS; part++) {
        cull->part_range[part] = range_of(cull, cull->part_group[part]);
        cull->part_kept[part] = 0;
    }
    cull->next = 0;
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    const uint32_t code = dr_parallel(test_part, cull);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    return code;
}

uint32_t dp_cull_pick(int core, uint32_t index, uint64_t arg) {
    (void)core;
    (void)index;
    dp_cull_t* cull = (dp_cull_t*)(uintptr_t)arg;
    uint32_t dealt = __atomic_fetch_add(&cull->next, 1u, __ATOMIC_RELAXED);
    for (uint32_t part = 0; part < DP_CULL_PARTS; part++) {
        if (dealt < cull->part_kept[part]) {
            return cull->survivors[cull->part_range[part] + dealt];
        }
        dealt -= cull->part_kept[part];
    }
    return KMX_PULL_NONE;
}
