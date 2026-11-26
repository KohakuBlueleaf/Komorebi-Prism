/* The field update as job commands of the job thread: its numbers region's words, the
 * job's input (written by the lead into the job's block), its codes, the commands and
 * the parts. The sizes, the times row's words and the steps are the build's FU_*
 * defines (read from indirect_field_update.h), the header's word places its FU_H_*. */
#pragma once

#include <stdint.h>

#include "jobs.h"

/* The region field_numbers: what the host gives the update (addresses, first pages,
 * the cores that copy) */
#define JF_N_CORES 0u        /* the cores that copy: ranks 0 to it - 1 */
#define JF_N_SHADOW 1u       /* the light pages' address, for the shadow map */
#define JF_N_SHADOW_FIRST 2u /* the shadow map's first light page */
#define JF_N_FIELD 3u        /* the light pages' address, for the field */
#define JF_N_FIELD_FIRST 4u  /* the first light page of the half the update writes */
#define JF_N_X 5u            /* x of the passes: its tensor's address */
#define JF_N_Y 6u            /* y of the passes: its tensor's address */
#define JF_N_WORDS 7u

/* The update's codes: the regions or words do not hold the update, or a step out of
 * turn; a fetch or a store did not finish */
#define JF_BAD_UPDATE (JB_JOB_CODES + 1u)
#define JF_COPY (JB_JOB_CODES + 2u)

/* The arrays' places (the header's offsets) the parts read */
#define JF_ELEMENT_ARRAYS 8u
#define JF_E_POSITION 0u
#define JF_E_NORMAL 1u
#define JF_E_BASE 2u
#define JF_E_ALBEDO 3u
#define JF_E_TRANSFER 4u
#define JF_E_STARTS 5u
#define JF_E_PAIRS 6u
#define JF_E_PLACES 7u
#define JF_WORK_ARRAYS 6u
#define JF_W_SKY 0u
#define JF_W_L0 1u
#define JF_W_TOTAL 2u
#define JF_W_X 3u
#define JF_W_Y 4u
#define JF_W_VALUES 5u

/* The job's input: one step's words, numbers and arrays' places, read by every part
 * from the job's block */
typedef struct {
    uint32_t n, tiles, rows, weights, pages_count, side, shadow_pages;
    uint32_t cores, shadow_at, shadow_first, field_at, field_first, x_at, y_at;
    uint32_t more; /* a pass: another pass follows (x made) */
    uint32_t element[JF_ELEMENT_ARRAYS], work[JF_WORK_ARRAYS];
    float texel, bias, sun[3], irradiance[3], camera[16], sky[FU_SKY_TERMS * 3];
    float scale;
} jf_job_t;

/* A part's view of the regions on its own cluster, and the job's input. */
typedef struct {
    const jf_job_t* job;
    const uint8_t* elements;
    const float* shadow;
    uint8_t* work;
    uint32_t* pages;
} jf_view_t;

/* A part's line of the job's block: its largest value's word, its bad count */
#define JF_GIVEN_TOP 0u
#define JF_GIVEN_BAD 1u

/* The job commands (the switch is generated): 0, or the code. Sources: the shadow map
 * fetched, sky, sun, L0, pass 1's x stored. Pass: y fetched, added, the next x stored
 * while passes remain. Finish: e, the rows, the scale, the texels, the pages stored.
 * Scale: the last finished update's scale, its float32's word (0 before the first). */
uint32_t job_field_sources(const km_command_t* command);
uint32_t job_field_pass(const km_command_t* command);
uint32_t job_field_finish(const km_command_t* command);
uint32_t job_field_scale(const km_command_t* command);

/* job_field_parts.c: a word's float32 and a float32's word */
float jf_word_float(uint32_t word);
uint32_t jf_float_word(float value);

/* job_field_parts.c: the parts, `index` of `of` (jb_parallel), each writing back what
 * it wrote. Sources: sky, sun, L0, pass 1's x, the total 0 of its tiles. Pass: E added
 * and the next x of its tiles. Source: e = total + sky of its tiles. Rows: its rows'
 * values and its largest. Zero (the first update): its lines of the pages and its
 * tiles of x. Pack: the texels of its lines of the pages. */
void jf_sources_part(uint32_t index, uint32_t of);
void jf_pass_part(uint32_t index, uint32_t of);
void jf_source_part(uint32_t index, uint32_t of);
void jf_rows_part(uint32_t index, uint32_t of);
void jf_zero_part(uint32_t index, uint32_t of);
void jf_pack_part(uint32_t index, uint32_t of);
