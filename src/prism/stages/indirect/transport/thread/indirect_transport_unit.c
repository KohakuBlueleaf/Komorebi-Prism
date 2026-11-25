/* The transport unit: APPLY built by the class's builder, run by the director, its
 * ticks, count and code kept. */
#include "indirect_transport_unit.h"

/* The results region's words: the command's ticks, count and code added. */
static void keep(uint32_t ticks, uint32_t code) {
    volatile uint32_t* words = (volatile uint32_t*)DR_REGION(
        DR_INDIRECT_TRANSPORT_REGION_TRANSPORT_RESULTS
    );
    const uint32_t least = words[TRANSPORT_R_TICKS_LEAST];
    words[TRANSPORT_R_TICKS] = ticks;
    words[TRANSPORT_R_TICKS_SUM] = words[TRANSPORT_R_TICKS_SUM] + ticks;
    words[TRANSPORT_R_TICKS_LEAST] = words[TRANSPORT_R_SERVED] == 0 || ticks < least
        ? ticks
        : least;
    words[TRANSPORT_R_SERVED] = words[TRANSPORT_R_SERVED] + 1;
    words[TRANSPORT_R_CODE] = code;
    dr_flush(
        DR_INDIRECT_TRANSPORT_REGION_TRANSPORT_RESULTS,
        DR_INDIRECT_TRANSPORT_REGION_TRANSPORT_RESULTS_AT,
        4u * TRANSPORT_R_WORDS
    );
}

uint32_t indirect_transport_unit_pass(dr_frame_t* frame) {
    uint64_t mark = kmx_time();
    dr_invalidate(DR_REGION_NUMBERS, 4u * DR_INDIRECT_TRANSPORT_N_TRANSPORT_CORES, 4u);
    const uint32_t cores = dr_number(frame, DR_INDIRECT_TRANSPORT_N_TRANSPORT_CORES);
    uint32_t code = DR_BAD_ARGS;
    if (cores != 0 && cores <= 0xFFFFu) {
        km_command_t command;
        DR_INDIRECT_TRANSPORT_BUILD(apply)(&command, 0, 0, cores);
        code = dr_run(&command);
    }
    keep(dr_ticks(&mark), code);
    return code;
}

uint32_t indirect_transport_unit_apply(dr_frame_t* frame, const km_command_t* command) {
    (void)command;
    return indirect_transport_unit_pass(frame);
}
