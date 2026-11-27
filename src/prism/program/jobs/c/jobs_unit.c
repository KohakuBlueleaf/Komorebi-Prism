/* The job thread's part of the frame's thread (jobs_unit.h). */
#include "jobs_unit.h"

/* What the last job_wants left (in .data: the image links no .bss). */
typedef struct {
    uint32_t given, half, scale;
} wants_t;

static wants_t g_wants __attribute__((section(".data"))) = {0, 0, 1u};

uint32_t jobs_unit_job_wants(dr_frame_t* frame, const km_command_t* command) {
    (void)frame;
    if (command->a0) {
        g_wants.half = command->a1;
        g_wants.scale = command->a2;
        g_wants.given = 1;
    }
    return 0;
}

uint32_t jobs_unit_field(uint32_t* half, uint32_t* scale) {
    *half = g_wants.half;
    *scale = g_wants.scale;
    return g_wants.given;
}

uint32_t jobs_unit_light_field(dr_frame_t* frame) {
    (void)frame;
    return g_wants.given ? 1u + g_wants.half : 0u;
}

uint32_t jobs_unit_light_field_scale(dr_frame_t* frame) {
    (void)frame;
    return g_wants.scale;
}
