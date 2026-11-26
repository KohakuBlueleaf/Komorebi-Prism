/* The job thread's part of the frame's thread (jobs_unit.h). */
#include "jobs_unit.h"

/* What the last job_wants left (in .data: the image links no .bss). */
typedef struct {
    uint32_t wanted, given, half, scale;
} wants_t;

static wants_t g_wants __attribute__((section(".data"))) = {0, 0, 0, 1u};

uint32_t jobs_unit_job_wants(dr_frame_t* frame, const km_command_t* command) {
    (void)frame;
    g_wants.wanted = command->a0;
    if (command->a1) {
        g_wants.half = command->a2;
        g_wants.scale = command->a3;
        g_wants.given = 1;
    }
    return 0;
}

uint32_t jobs_unit_cores_wanted(void) {
    return g_wants.wanted;
}

uint32_t jobs_unit_frame_first(uint32_t cores) {
    return g_wants.wanted < cores ? g_wants.wanted : 0u;
}

uint32_t jobs_unit_field(uint32_t* half, uint32_t* scale) {
    *half = g_wants.half;
    *scale = g_wants.scale;
    return g_wants.given;
}
