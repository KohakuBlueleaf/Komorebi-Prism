/* The director: the frame's thread runtime. Its types, its codes and the calls a unit
 * makes; the places and ids are the generated pipeline.h's. */
#pragma once

#include <stdint.h>

#include "kmx.h"
#include "pipeline.h"

/* A thread command's result: 0, a runtime code, or a unit's (above DR_UNIT_CODES) */
#define DR_BAD_ARGS 1u /* a number, a region or a word out of its range */
#define DR_RING 2u     /* a command could not be submitted or its event did not come */
#define DR_COMMAND 3u  /* a command did not finish (timeout, rejected) */
#define DR_PARALLEL 4u /* a part on the four cores did not finish (late, stopped) */
#define DR_UNIT_CODES 16u

#define DR_WAIT_TICKS KMX_TICKS_PER_SECOND /* a submit's and a wait's give-up */

/* A core step: on a cluster other than the frame's (DR_CORE_STEP, its number of the
 * frame cluster's command core_step), dr_submit sends a core command to the director
 * as core_step's words: a0 its header, a1 its group, a2 to a9 its a0 to a7 (its a8 and
 * a9 must be 0); the director runs it (dr_run) between two commands and answers its
 * code in the low DR_STEP_CODE_BITS, its own ticks for it above them; dr_wait writes a
 * times row a step: `frame` the round trip, `core_step` the director's ticks, `code` */
#define DR_STEP_CODE_BITS 8u
#define DR_STEP_CODE_MASK 0xFFu
#define DR_STEP_TICKS_MOST 0xFFFFFFu
#define DR_STEP_ARGS 8u  /* the core command's words a core step carries: a0 to a7 */
#define DR_STEPS_HELD 8u /* core steps in flight at once on a cluster */
/* core commands in flight at once that are submitted again after a busy rejection */
#define DR_LINES_HELD 8u

/* A view's kind: COLOUR (the eye's: every unit does its work) or DEPTH (its product the
 * nearest surface's 1/z, into its target) */
#define DR_VIEW_COLOUR 0u
#define DR_VIEW_DEPTH 1u

/* A view of the frame: its index (0 the eye's; its camera areas and layer rows are
 * index times DR_LAYERS plus the layer), its kind, its camera's words and their bank
 * address, its grid word (the commands') and tiles; a DEPTH view's target: a tensor,
 * its first page, its pages a row of tiles, its pages */
typedef struct {
    uint32_t index, kind;
    uint32_t camera[DR_N_CAMERA_WORDS];
    uint32_t camera_at;
    uint32_t grid, tiles;
    uint32_t target, target_first, target_across, target_pages;
} dr_view_t;

/* A layer of a view: its row of the layers region (DR_LAYER_WORDS, by DR_<UNIT>_L_*) */
typedef struct {
    uint32_t index;
    const volatile uint32_t* words;
} dr_layer_t;

/* The runtime's one frame state: the numbers, the cores, this frame's times row (times
 * and results, by DR_<UNIT>_T_* and DR_<UNIT>_R_*; a layer unit's by dr_layer_time),
 * the region table */
typedef struct {
    const volatile uint32_t* numbers;
    uint32_t bank_plus_one, cores, workers, layers;
    uint32_t times[DR_TIMES_WORDS];
    uint32_t served, set_up;
    void* regions[DR_REGIONS];
    uint32_t address[DR_REGIONS];
    uint64_t bytes[DR_REGIONS];
} dr_frame_t;

/* A shared region is a part of the numbers region: these apply its offset */
#define DR_REGION(name) dr_region(name, name##_AT)
#define DR_ADDRESS(name) dr_address(name, name##_AT)

/* Submits `command` (again while the ring is full, for DR_WAIT_TICKS at most): 0 with
 * its handle, or DR_RING; on another cluster as a core step (DR_BAD_ARGS for words a8
 * or a9, DR_RING with DR_STEPS_HELD in flight). */
uint32_t dr_submit(const km_command_t* command, uint32_t* handle);

/* Waits for a submitted command's event: 0, DR_RING or DR_COMMAND; a command rejected
 * busy (another source's command held the slot) is submitted again at the dispatcher's
 * next wake, within DR_WAIT_TICKS of its first submit (the times row's `resubmits` and
 * `wake_ticks` count them and the ticks waited since the load, `wake_most` the longest
 * wait in the row). On another cluster a core step's: the director's code, DR_RING or
 * DR_COMMAND. */
uint32_t dr_wait(uint32_t handle);

/* dr_submit, then dr_wait. */
uint32_t dr_run(const km_command_t* command);

/* Timer ticks since `*mark`, which becomes now. */
uint32_t dr_ticks(uint64_t* mark);

/* Region `id` as memory, and its bank address, from byte `at`. */
void* dr_region(uint32_t id, uint32_t at);
uint32_t dr_address(uint32_t id, uint32_t at);

/* The lines of region `id` holding `bytes` from `at`: written back, or dropped. */
void dr_flush(uint32_t id, uint32_t at, uint32_t bytes);
void dr_invalidate(uint32_t id, uint32_t at, uint32_t bytes);

/* A number of the numbers region, by its place (DR_<UNIT>_N_*). */
uint32_t dr_number(const dr_frame_t* frame, uint32_t place);

/* A layer unit's word of this frame's times row, of `layer`: a time or a result by its
 * place (DR_<UNIT>_T_*, DR_<UNIT>_R_*), DR_TIMES_LAYER_WORDS a layer. */
uint32_t* dr_layer_time(dr_frame_t* frame, const dr_layer_t* layer, uint32_t place);

/* A command's word at `place` (0 to 9: a0 to a9), as the generated header's places. */
void dr_word(km_command_t* command, uint32_t place, uint32_t value);

/* `function(core, arg)` on the four cores (kmx_parallel): 0, or DR_PARALLEL. */
uint32_t dr_parallel(void (*function)(int core, void* arg), void* arg);

/* Parts of one region swept (dropped; a dirty line is also written back) in one
 * dr_parallel, part i on core i % 4. A part is `repeats` spans of `bytes`, the first at
 * `at` and each `stride` after the last. */
#define DR_SWEEP_PARTS 8

typedef struct {
    uint32_t region, count;
    uint64_t at[DR_SWEEP_PARTS], bytes[DR_SWEEP_PARTS];
    uint64_t stride[DR_SWEEP_PARTS];
    uint32_t repeats[DR_SWEEP_PARTS];
} dr_sweep_t;

void dr_sweep_start(dr_sweep_t* sweep, uint32_t region);
/* [at, at + bytes) as one part (one span) */
void dr_sweep_add(dr_sweep_t* sweep, uint64_t at, uint64_t bytes);
/* `repeats` spans of `bytes` from `at`, `stride` apart, as one part */
void dr_sweep_strided(
    dr_sweep_t* sweep, uint64_t at, uint64_t bytes, uint64_t stride, uint32_t repeats
);
/* [at, at + bytes) as two parts (two cores) */
void dr_sweep_halves(dr_sweep_t* sweep, uint64_t at, uint64_t bytes);
uint32_t dr_sweep_run(dr_sweep_t* sweep);

/* The numbers read and, once, the units set up: 0, or the code. A served command's
 * first call when it runs views, before its row is started. */
uint32_t dr_ready(dr_frame_t* frame);

/* A times row begun (every word 0): its start. A served command that runs views
 * writes a row as FRAME does (the host counts it as a row). */
uint64_t dr_row_start(dr_frame_t* frame);

/* The row ended: its time since `started`, `code`, its number, into the times region
 * (the last DR_TIMES_ROWS kept). `code`. */
uint32_t dr_row_end(dr_frame_t* frame, uint32_t code, uint64_t started);

/* The FRAME command: the eye's view from the numbers, dr_view, the times row. */
uint32_t dr_serve_frame(dr_frame_t* frame);

#ifdef DR_COMMAND_CORE_STEP
/* The command core_step: another cluster's core command run (dr_run); its code and
 * the ticks it took, as DR_STEP_CODE_BITS says. */
uint32_t dr_serve_core_step(dr_frame_t* frame, const km_command_t* command);
#endif

/* The runtime's frame state. */
dr_frame_t* dr_state(void);

/* Generated (pipeline.c): each unit's setup in the pipeline's order. */
uint32_t dr_units_setup(dr_frame_t* frame);

/* Generated (pipeline.c): a view, unit by unit, each layer then the frame (a DEPTH view
 * without the layers whose column DR_L_DEPTH is 0); the first code that is not 0 ends
 * it. The FRAME command's for the eye's; a unit's for views it builds. */
uint32_t dr_view(dr_frame_t* frame, const dr_view_t* view);

/* Generated (pipeline.h): each function a unit gives a slot by, called by its
 * DR_GIVE_<SLOT> name. */
DR_GIVES_DECLARED
