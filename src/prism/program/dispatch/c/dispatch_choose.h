/* The tile pull's choice: the next tile thread for the core that asks, by one of three
 * policies, from a few words a slice and a core kept in the frame cluster's memory.
 * Plain C: built into the frame's thread and, for the check, on the host. */
#pragma once

#include <stdint.h>

#include "kmx.h"
#include "thread/answer.h"
#include "thread/record.h"

#ifndef DP_SLICES_MOST
#error "DP_SLICES_MOST: the slices a view holds at most, the capacity's"
#endif

/* The policies (a number of the load) */
#define DP_POLICY_PREFER 0u /* near the core's last slice, heaviest first, else any */
#define DP_POLICY_ORDER 1u  /* the slices in order, each slice's records in order */
#define DP_POLICY_KEPT 2u   /* slice s to the rank s mod the group's cores, kept */
#define DP_POLICIES 3u

#define DP_NO_SLICE 0xFFFFFFFFu /* a core's last slice before its first thread */

/* A slice: its records, the next place to hand (an atomic counter), its weight, its
 * place in the slice grid (row, column) */
#define DP_SLICE_WORDS 8u

typedef struct {
    uint32_t records, next, weight, row, column;
    uint32_t spare[DP_SLICE_WORDS - 5u];
} dp_slice_t;

/* A core: its last slice, and its newest tell: the codes it holds, the cost of the
 * thread that ended, the number of tells taken */
#define DP_CORE_WORDS 4u

typedef struct {
    uint32_t last, codes, cost, tells;
} dp_core_t;

/* The choice's state: the policy, the "near" distance in slices, the slices, the
 * group's first rank and cores, the order policy's first slice not yet empty, the
 * answers marked near; each core's words, each slice's words */
#define DP_CHOOSE_HEAD_WORDS 8u

typedef struct {
    uint32_t policy, near, slices, first, count, cursor, near_given;
    uint32_t spare;
    dp_core_t core[KMX_PORTS_CORES];
    dp_slice_t slice[DP_SLICES_MOST];
} dp_choose_t;

#define DP_CHOOSE_BYTES                                        \
    (4u *                                                      \
     (DP_CHOOSE_HEAD_WORDS + DP_CORE_WORDS * KMX_PORTS_CORES + \
      DP_SLICE_WORDS * DP_SLICES_MOST))

/* The state set for a view: the policy, the near distance, the group, the slices,
 * `across` a row of the slice grid; every slice empty, every core without a last
 * slice. 0, or 1 for a policy, a group or slices out of range. */
uint32_t dp_choose_reset(
    dp_choose_t* state,
    uint32_t policy,
    uint32_t near,
    uint32_t first,
    uint32_t count,
    uint32_t slices,
    uint32_t across
);

/* Slice `slice`'s records and weight, as its sum wrote them. */
void dp_choose_slice(
    dp_choose_t* state, uint32_t slice, uint32_t records, uint32_t weight
);

/* kmx_pull's pick_word: `core`'s next tile thread, TR_NUMBER(slice, place), with its
 * word TA_WORD(code, hint), or KMX_PULL_NONE when the policy leaves the core none.
 * `arg` the state. Never waits; bounded by the slices. */
uint64_t dp_choose(int core, uint32_t index, uint64_t arg);
