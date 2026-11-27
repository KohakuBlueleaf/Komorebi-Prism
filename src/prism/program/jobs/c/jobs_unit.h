/* The job thread's part of the frame's thread: the command `job_wants` a job's graph
 * sends (served between two of the frame's commands), the field made last. */
#pragma once

#include <stdint.h>

#include "director.h"

/* job_wants's words: a0 1 when a1 and a2 give a field just made, a1 the half of the
 * field's pages it is in, a2 its scale's word */
#define JOBS_WANTS_FIELD 0u
#define JOBS_WANTS_HALF 1u
#define JOBS_WANTS_SCALE 2u

/* The thread command `job_wants`: with a0 the field's half and scale kept. 0. */
uint32_t jobs_unit_job_wants(dr_frame_t* frame, const km_command_t* command);

/* The field made last: the half of the field's pages it is in and its scale's word;
 * 0 before the first job gave one, 1 after. */
uint32_t jobs_unit_field(uint32_t* half, uint32_t* scale);

/* The slot light.field: 1 + the half of the field's pages the field made last is in,
 * 0 before the first job gave one. */
uint32_t jobs_unit_light_field(dr_frame_t* frame);

/* The slot light.field_scale: the field made last's scale word. */
uint32_t jobs_unit_light_field_scale(dr_frame_t* frame);
