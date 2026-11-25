/* The field update's thread unit: the command `update` (a0 the step) makes the field
 * after a light change: the sources from the shadow map and the elements, each pass's
 * apply by the slot elements.irradiance's giver, the field's rows and its pages. The
 * parts on the four cores are indirect_field_update_parts.c's. */
#pragma once

#include <stdint.h>

#include "director.h"
#include "indirect_field_update.h"

/* The unit's regions and numbers by short names (the layout's macros) */
#define FU_R_HEADER DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_HEADER
#define FU_R_HEADER_AT DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_HEADER_AT
#define FU_R_ELEMENTS DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_ELEMENTS
#define FU_R_ELEMENTS_AT DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_ELEMENTS_AT
#define FU_R_SHADOW DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_SHADOW
#define FU_R_SHADOW_AT DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_SHADOW_AT
#define FU_R_WORK DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_WORK
#define FU_R_WORK_AT DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_WORK_AT
#define FU_R_PAGES DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_PAGES
#define FU_R_PAGES_AT DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_PAGES_AT
#define FU_R_TIMES DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_TIMES
#define FU_R_TIMES_AT DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_TIMES_AT
#define FU_N_CORES DR_INDIRECT_FIELD_UPDATE_N_UPDATE_CORES
#define FU_N_SHADOW DR_INDIRECT_FIELD_UPDATE_N_UPDATE_SHADOW
#define FU_N_SHADOW_FIRST DR_INDIRECT_FIELD_UPDATE_N_UPDATE_SHADOW_FIRST
#define FU_N_FIELD DR_INDIRECT_FIELD_UPDATE_N_UPDATE_FIELD
#define FU_N_FIELD_FIRST DR_INDIRECT_FIELD_UPDATE_N_UPDATE_FIELD_FIRST
#define FU_N_X DR_INDIRECT_FIELD_UPDATE_N_UPDATE_X
#define FU_N_Y DR_INDIRECT_FIELD_UPDATE_N_UPDATE_Y

/* One step's view of the regions, words and numbers, for the parts on the four
 * cores. */
typedef struct {
    const volatile uint32_t* header;
    const uint8_t* elements;
    const float* shadow;
    uint8_t* work;
    uint32_t* pages;
    uint32_t n, tiles, rows, weights, pages_count, side;
    uint32_t cores, shadow_at, shadow_first, field_at, field_first, x_at, y_at;
    uint32_t more; /* step 2: another pass follows (x made) */
    float texel, bias, sun[3], irradiance[3], camera[16], sky[FU_SKY_TERMS * 3];
    float scale;
    float top[4];    /* each core's largest value */
    uint32_t bad[4]; /* each core's columns, starts or places out of range */
} fu_job_t;

/* The thread command `update` (step `command->a0`): 0, or the code. */
uint32_t indirect_field_update_unit_update(
    dr_frame_t* frame, const km_command_t* command
);

/* The thread command `field_scale`: the last finished update's scale, its float32's
 * word (0 before the first). */
uint32_t indirect_field_update_unit_field_scale(
    dr_frame_t* frame, const km_command_t* command
);

/* indirect_field_update_parts.c: a word's float32 and a float32's word */
float fu_word_float(uint32_t word);
uint32_t fu_float_word(float value);

/* indirect_field_update_parts.c: the parts on the four cores, `arg` the job. Step 1:
 * sky, sun, L0, pass 1's x, the total 0; step 2: E added, the next x; step 3: e =
 * total + sky, the rows' values and each core's largest, the texels; the first update:
 * the pages and x zeroed. */
void fu_sources_part(int core, void* arg);
void fu_pass_part(int core, void* arg);
void fu_source_part(int core, void* arg);
void fu_rows_part(int core, void* arg);
void fu_zero_part(int core, void* arg);
void fu_pack_part(int core, void* arg);
