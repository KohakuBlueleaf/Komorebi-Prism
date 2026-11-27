/* The count ranges a view deals: a box a group of consecutive ranges (the region
 * DP_REGION_GROUP_BOXES, written by the host) tested against the view before the count
 * pull (prism_reference.raster.cull), on the cluster's cores; the ranges of a group
 * wholly behind the near distance or past an edge of the padded frame for every point
 * in front of it are never dealt. A dealt range's own box is tested by the core that
 * takes it. */
#pragma once

#include <stdint.h>

#include "dispatch.h"

/* A group's box: the least corner's x, y, z, then the most corner's (float32) */
#define DP_BOX_WORDS 6u

/* The X280 cores that test a view's groups, a share of them each */
#define DP_CULL_PARTS 4u

/* A view's deal: the next survivor to deal; the view's ranges and groups, the ranges a
 * group holds, its layers' first ranges, first groups in the view and first boxes in
 * the region (each then the view's totals); the view's camera and padded frame; the
 * boxes; the survivors (the ranges of the groups not cut, in order: each part's from
 * the first range of its first group on), each part's first group, first range and
 * survivors */
typedef struct {
    volatile uint32_t next;
    uint32_t ranges, groups, group_ranges, layers;
    uint32_t range_first[TR_LAYERS + 1u];
    uint32_t group_first[TR_LAYERS + 1u];
    uint32_t box_first[TR_LAYERS];
    float camera[DR_N_CAMERA_WORDS];
    float width, height;
    const float* boxes;
    uint32_t* survivors;
    uint32_t part_group[DP_CULL_PARTS + 1u], part_range[DP_CULL_PARTS];
    uint32_t part_kept[DP_CULL_PARTS];
} dp_cull_t;

/* Whether `box` (DP_BOX_WORDS) lies outside the view of `camera` (16 float32) on a
 * padded frame of `width` x `height` pixels. */
uint32_t dp_box_outside(
    const float* camera, const float* box, float width, float height
);

/* Core 0: every group of the view tested, DP_CULL_PARTS shares on the cluster's cores,
 * the survivors written. 0, or the director's code. */
uint32_t dp_cull_test(dp_cull_t* cull);

/* The count pull's pick (kmx_pull.pick, `arg` the dp_cull_t): the next survivor, or
 * KMX_PULL_NONE. */
uint32_t dp_cull_pick(int core, uint32_t index, uint64_t arg);
