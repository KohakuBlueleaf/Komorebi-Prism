/* The job thread's part of the frame's thread: the command `job_wants` a job's graph
 * sends (served between two of the frame's commands), the cores an update waiting
 * wants, the ranks the frame's pulls take, the field made last. */
#pragma once

#include <stdint.h>

#include "director.h"

/* job_wants's words: a0 the cores the job wants (0: none), a1 1 when a2 and a3 give a
 * field just made, a2 the half of the field's pages it is in, a3 its scale's word */
#define JOBS_WANTS_CORES 0u
#define JOBS_WANTS_FIELD 1u
#define JOBS_WANTS_HALF 2u
#define JOBS_WANTS_SCALE 3u

/* The thread command `job_wants`: the wanted cores kept, and with a1 the field's half
 * and scale. 0. */
uint32_t jobs_unit_job_wants(dr_frame_t* frame, const km_command_t* command);

/* The cores an update waiting wants (0: none). */
uint32_t jobs_unit_cores_wanted(void);

/* The first rank of the frame's pulls on `cores` cores: the wanted cores when fewer
 * than `cores` are wanted, else 0 (the job then gets the cores between two frames). */
uint32_t jobs_unit_frame_first(uint32_t cores);

/* The field made last: the half of the field's pages it is in and its scale's word;
 * 0 before the first job gave one, 1 after. */
uint32_t jobs_unit_field(uint32_t* half, uint32_t* scale);

/* The slot light.field: 1 + the half of the field's pages the field made last is in,
 * 0 before the first job gave one. */
uint32_t jobs_unit_light_field(dr_frame_t* frame);

/* The slot light.field_scale: the field made last's scale word. */
uint32_t jobs_unit_light_field_scale(dr_frame_t* frame);
