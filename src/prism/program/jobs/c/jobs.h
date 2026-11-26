/* The job thread's runtime: one image on every cluster of the job thread, the lowest
 * (kmx_lead) answering job commands, the others serving its kmx_parallel_all calls.
 * Its codes, the job's block, the parts over every core, the copies, the regions; the
 * handlers and region ids are the generated jobs_layout.h's. */
#pragma once

#include <stdint.h>

#include "jobs_layout.h"
#include "kmx.h"

/* A job command's result: 0, a runtime code, or a job's (above JB_JOB_CODES) */
#define JB_BAD_ARGS 1u /* a region, a word or a number out of its range */
#define JB_RING 2u     /* a copy could not be submitted or its event did not come */
#define JB_PARALLEL 3u /* the parts did not finish (late, stopped) */
#define JB_PEERS 4u    /* the other clusters of the image did not come to serve */
#define JB_NOT_LEAD 5u /* a job command to a cluster that is not the lead */
#define JB_JOB_CODES 16u

#define JB_WAIT_TICKS KMX_TICKS_PER_SECOND         /* a copy's give-up */
#define JB_PEERS_TICKS (4u * KMX_TICKS_PER_SECOND) /* the peers' first serve */

/* The job's block: the region JB_REGION_JOBS_BLOCK. Its first JB_BLOCK_IN bytes the
 * lead writes before the parts: the job's input (JB_INPUT_BYTES), a drop's ranges
 * (JB_DROP_AT), the call (its last line); then a line a part for what it gives back
 * (JB_PARTS_MOST lines) */
#define JB_BLOCK_IN 2048u
#define JB_LINE 64u
#define JB_INPUT_BYTES 1792u
#define JB_DROP_AT JB_INPUT_BYTES
#define JB_CALL_AT (JB_BLOCK_IN - JB_LINE)
#define JB_CORES 4u       /* X280 cores a cluster */
#define JB_PARTS_MOST 12u /* three clusters of four cores */
#define JB_BLOCK_BYTES (JB_BLOCK_IN + JB_PARTS_MOST * JB_LINE)

/* A part of a job: `index` of `of` (every core of every cluster of the image, the
 * lead's cores first). */
typedef void (*jb_part_t)(uint32_t index, uint32_t of);

/* The regions a part or the lead reads, dropped on every cluster before the parts
 * (each range split over a cluster's four cores) */
#define JB_DROP_RANGES 8u

typedef struct {
    uint32_t count;
    uint32_t region[JB_DROP_RANGES];
    uint64_t at[JB_DROP_RANGES], bytes[JB_DROP_RANGES];
} jb_drop_t;

/* The runtime's state on each cluster: its regions, its setup's code, the parts. */
typedef struct {
    void* regions[JB_REGIONS];
    uint64_t bytes[JB_REGIONS];
    uint32_t address[JB_REGIONS];
    uint32_t set_up, peers, parts, lead;
} jb_state_t;

jb_state_t* jb_state(void);

/* Region `id` as memory from byte `at`, its bytes, its bank address. */
void* jb_region(uint32_t id, uint64_t at);
uint64_t jb_region_bytes(uint32_t id);
uint32_t jb_region_address(uint32_t id);

/* The lines of region `id` holding `bytes` from `at`, on this cluster: written back
 * (flush), or written back and dropped (invalidate). Core 0 outside the parts spreads
 * them over the four cores; a part's core does its own. */
void jb_flush(uint32_t id, uint64_t at, uint64_t bytes);
void jb_invalidate(uint32_t id, uint64_t at, uint64_t bytes);

/* The job's input (the block's first JB_INPUT_BYTES), and part `index`'s line. */
void* jb_input(void);
uint32_t* jb_given(uint32_t index);

/* The lead's core 0: the input written back, then `part(index, of)` on every core of
 * every cluster, each cluster reading the input afresh; the parts' lines read back
 * after. 0, or JB_PARALLEL. A part writes back what it wrote (jb_flush) before it
 * returns. */
uint32_t jb_parallel(jb_part_t part);

/* The parts a job is split into (four a cluster of the image). */
uint32_t jb_parts(void);

/* The lead's core 0: the ranges of `drop` written back and dropped on every cluster of
 * the image (each range over a cluster's four cores). 0, or JB_PARALLEL. */
void jb_drop_start(jb_drop_t* drop);
void jb_drop_add(jb_drop_t* drop, uint32_t region, uint64_t at, uint64_t bytes);
uint32_t jb_drop_run(jb_drop_t* drop);

/* The first and the end of part `index` of `of` over `count` units, each a multiple
 * of `grain` but the last end (`count`). */
void jb_share(
    uint32_t index,
    uint32_t of,
    uint64_t count,
    uint64_t grain,
    uint64_t* first,
    uint64_t* end
);

/* The lead's core 0: cores [first, first + count) copy `bytes` from `from` into region
 * `id` at `at` (kmx_fetch), or the other way (kmx_store), within JB_WAIT_TICKS. 0, or
 * JB_RING. */
uint32_t jb_fetch(
    uint32_t id,
    uint64_t at,
    const kmx_dram* from,
    uint64_t bytes,
    uint32_t first,
    uint32_t count
);
uint32_t jb_store(
    uint32_t id,
    uint64_t at,
    const kmx_dram* to,
    uint64_t bytes,
    uint32_t first,
    uint32_t count
);

/* Timer ticks since `*mark`, which becomes now. */
uint32_t jb_ticks(uint64_t* mark);

/* The lead's job command `command` checked: 0 when the runtime is set up, this cluster
 * is the lead and the peers serve; else the code. */
uint32_t jb_ready(void);

/* The runtime's command JOBS_SERVE on a cluster that is not the lead: the lead's
 * kmx_parallel_all calls served until the run stops. 0, or the code. */
uint32_t jb_serve(const km_command_t* command);
