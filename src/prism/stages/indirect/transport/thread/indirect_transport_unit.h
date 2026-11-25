/* The transport's thread unit: one APPLY on the cores (the class's builder), as the
 * function that gives the slot elements.irradiance and as the served command `apply`;
 * each one's ticks, count and code in the unit's results region. */
#pragma once

#include <stdint.h>

#include "director.h"

/* The results region's words: the last command's ticks, their sum and least, the
 * commands run, the last code */
#define TRANSPORT_R_TICKS 0u
#define TRANSPORT_R_TICKS_SUM 1u
#define TRANSPORT_R_TICKS_LEAST 2u
#define TRANSPORT_R_SERVED 3u
#define TRANSPORT_R_CODE 4u
#define TRANSPORT_R_WORDS 5u

/* One APPLY on cores 0 to the number `transport_cores` - 1, waited for: 0, or the
 * code. */
uint32_t indirect_transport_unit_pass(dr_frame_t* frame);

/* The thread command `apply`: one pass. 0, or the code. */
uint32_t indirect_transport_unit_apply(dr_frame_t* frame, const km_command_t* command);
