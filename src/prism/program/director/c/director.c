/* The director's runtime: the region table at the start, the FRAME command, submit,
 * wait and run, ticks, regions, numbers and sweeps (director.h). */
#include "director.h"

/* The thread's state, kept from kmx_main for the commands (in .data: the image links
 * no .bss). */
static dr_frame_t g_frame __attribute__((section(".data"))) = {0};
/* units set up (at the first FRAME command, once the host wrote the numbers) */
static uint32_t g_ready __attribute__((section(".data"))) = 0;

dr_frame_t* dr_state(void) {
    return &g_frame;
}

/* `command` into the ring, again while it is full, for DR_WAIT_TICKS at most: 0 with
 * its handle, or DR_RING. */
static uint32_t submit_line(const km_command_t* command, uint32_t* handle) {
    const uint64_t until = kmx_time() + DR_WAIT_TICKS;
    int error = kmx_submit(command, handle);
    while (error == KMX_FULL && kmx_time() < until && !kmx_stop_requested()) {
        error = kmx_submit(command, handle);
    }
    return error == KMX_OK ? 0u : DR_RING;
}

/* Core commands submitted again after a busy rejection, since the load (in .data: the
 * image links no .bss). */
static uint32_t g_resubmits __attribute__((section(".data"))) = 0;
/* Ticks spent waiting for the dispatcher's wake after them, since the load. */
static uint32_t g_wake_ticks __attribute__((section(".data"))) = 0;

#ifndef DR_CORE_STEP
/* The commands in flight: their handles (0: a free place), words and first submits'
 * times, for a submit again after a busy rejection (in .data: the image links no
 * .bss). */
static uint32_t g_line_handle[DR_LINES_HELD] __attribute__((section(".data"))) = {0};
static uint32_t g_line_words[DR_LINES_HELD][16]
    __attribute__((section(".data"))) = {{0}};
static uint64_t g_line_start[DR_LINES_HELD] __attribute__((section(".data"))) = {0};

/* The 16 words of `from` into `to` (a loop: a struct copy may call memcpy). */
static void copy_line(volatile uint32_t* to, const volatile uint32_t* from) {
    for (uint32_t i = 0; i < 16; i++) {
        to[i] = from[i];
    }
}

/* The dispatcher's next wake event by `until`: 0, or DR_RING (late, stopped). */
static uint32_t wake(uint64_t until) {
    kmx_event event;
    while (kmx_time() < until && !kmx_stop_requested()) {
        if (kmx_poll(&event) == KMX_OK && event.kind == KMX_EVENT_WAKE) {
            return 0;
        }
    }
    return DR_RING;
}

uint32_t dr_submit(const km_command_t* command, uint32_t* handle) {
    uint32_t place = 0;
    while (place < DR_LINES_HELD && g_line_handle[place] != 0) {
        place++;
    }
    const uint64_t started = kmx_time();
    const uint32_t code = submit_line(command, handle);
    if (code == 0 && place < DR_LINES_HELD) {
        g_line_handle[place] = *handle;
        g_line_start[place] = started;
        copy_line(g_line_words[place], (const volatile uint32_t*)command);
    }
    return code;
}

uint32_t dr_wait(uint32_t handle) {
    uint32_t place = 0;
    while (place < DR_LINES_HELD && g_line_handle[place] != handle) {
        place++;
    }
    const uint64_t until = (place < DR_LINES_HELD ? g_line_start[place] : kmx_time()) +
        DR_WAIT_TICKS;
    uint32_t code = DR_COMMAND;
    for (;;) {
        kmx_event event;
        if (kmx_wait(handle, until, &event) != KMX_OK) {
            code = DR_RING;
            break;
        }
        if (event.kind == KM_EVENT_DONE) {
            code = 0;
            break;
        }
        if (place == DR_LINES_HELD || event.kind != KM_EVENT_REJECTED ||
            event.auxiliary != KMX_REJECT_BUSY) {
            break;
        }
        uint64_t mark = kmx_time();
        const uint32_t late = wake(until);
        const uint32_t waited = dr_ticks(&mark);
        g_wake_ticks += waited;
        if (waited > g_frame.times[DR_R_WAKE_MOST]) {
            g_frame.times[DR_R_WAKE_MOST] = waited;
        }
        if (late || kmx_time() >= until) {
            break;
        }
        km_command_t again;
        copy_line((volatile uint32_t*)&again, g_line_words[place]);
        if (submit_line(&again, &handle)) {
            code = DR_RING;
            break;
        }
        g_resubmits++;
    }
    if (place < DR_LINES_HELD) {
        g_line_handle[place] = 0;
    }
    return code;
}
#else
/* The core steps in flight: their handles (0: a free place) and submits' times (in
 * .data: the image links no .bss). */
static uint32_t g_step_handle[DR_STEPS_HELD] __attribute__((section(".data"))) = {0};
static uint64_t g_step_start[DR_STEPS_HELD] __attribute__((section(".data"))) = {0};

uint32_t dr_submit(const km_command_t* command, uint32_t* handle) {
    uint32_t place = 0;
    while (place < DR_STEPS_HELD && g_step_handle[place] != 0) {
        place++;
    }
    if (command->a8 != 0 || command->a9 != 0) {
        return DR_BAD_ARGS;
    }
    if (place == DR_STEPS_HELD) {
        return DR_RING;
    }
    km_command_t step;
    kmx_command(
        &step, 0, DR_CORE_STEP, KM_GROUP_CLUSTER_BASE + DR_CORE_STEP_CLUSTER, 1
    );
    step.hdr |= KM_FLAG_RESULT << 8;
    step.a0 = command->hdr;
    step.a1 = command->group;
    step.a2 = command->a0;
    step.a3 = command->a1;
    step.a4 = command->a2;
    step.a5 = command->a3;
    step.a6 = command->a4;
    step.a7 = command->a5;
    step.a8 = command->a6;
    step.a9 = command->a7;
    const uint64_t started = kmx_time();
    const uint32_t code = submit_line(&step, handle);
    if (code == 0) {
        g_step_handle[place] = *handle;
        g_step_start[place] = started;
    }
    return code;
}

uint32_t dr_wait(uint32_t handle) {
    uint64_t started = kmx_time();
    for (uint32_t place = 0; place < DR_STEPS_HELD; place++) {
        if (g_step_handle[place] == handle) {
            started = g_step_start[place];
            g_step_handle[place] = 0;
        }
    }
    kmx_event event;
    uint32_t code = DR_RING, director = 0;
    if (kmx_wait(handle, kmx_time() + DR_WAIT_TICKS, &event) == KMX_OK) {
        code = event.kind == KM_EVENT_DONE ? event.ticks & DR_STEP_CODE_MASK
                                           : DR_COMMAND;
        director = event.kind == KM_EVENT_DONE ? event.ticks >> DR_STEP_CODE_BITS : 0u;
    }
    dr_frame_t* frame = &g_frame;
    for (uint32_t i = 0; i < DR_TIMES_WORDS; i++) {
        frame->times[i] = 0;
    }
    frame->times[DR_T_CORE_STEP] = director;
    return dr_row_end(frame, code, started);
}
#endif

#ifdef DR_COMMAND_CORE_STEP
uint32_t dr_serve_core_step(dr_frame_t* frame, const km_command_t* command) {
    (void)frame;
    if ((command->a1 & 0xFFFFu) >= KM_GROUP_CLUSTER_BASE) {
        return DR_BAD_ARGS;
    }
    km_command_t step;
    step.sequence = 0;
    step.hdr = command->a0;
    step.group = command->a1;
    step.land1 = step.land2 = step.land3 = 0;
    step.a0 = command->a2;
    step.a1 = command->a3;
    step.a2 = command->a4;
    step.a3 = command->a5;
    step.a4 = command->a6;
    step.a5 = command->a7;
    step.a6 = command->a8;
    step.a7 = command->a9;
    step.a8 = step.a9 = 0;
    uint64_t mark = kmx_time();
    const uint32_t code = dr_run(&step);
    const uint32_t ticks = dr_ticks(&mark);
    return code |
        (ticks < DR_STEP_TICKS_MOST ? ticks : DR_STEP_TICKS_MOST) << DR_STEP_CODE_BITS;
}
#endif

uint32_t dr_run(const km_command_t* command) {
    uint32_t handle;
    const uint32_t code = dr_submit(command, &handle);
    return code ? code : dr_wait(handle);
}

uint32_t dr_ticks(uint64_t* mark) {
    const uint64_t now = kmx_time();
    const uint32_t ticks = (uint32_t)(now - *mark);
    *mark = now;
    return ticks;
}

void* dr_region(uint32_t id, uint32_t at) {
    return (uint8_t*)g_frame.regions[id] + at;
}

uint32_t dr_address(uint32_t id, uint32_t at) {
    return g_frame.address[id] + at;
}

void dr_flush(uint32_t id, uint32_t at, uint32_t bytes) {
    kmx_flush_at((int)id, at, bytes);
}

void dr_invalidate(uint32_t id, uint32_t at, uint32_t bytes) {
    kmx_invalidate_at((int)id, at, bytes);
}

uint32_t dr_number(const dr_frame_t* frame, uint32_t place) {
    return frame->numbers[place];
}

uint32_t* dr_layer_time(dr_frame_t* frame, const dr_layer_t* layer, uint32_t place) {
    return &frame->times[place + layer->index * DR_TIMES_LAYER_WORDS];
}

void dr_word(km_command_t* command, uint32_t place, uint32_t value) {
    switch (place) {
        case 0:
            command->a0 = value;
            break;
        case 1:
            command->a1 = value;
            break;
        case 2:
            command->a2 = value;
            break;
        case 3:
            command->a3 = value;
            break;
        case 4:
            command->a4 = value;
            break;
        case 5:
            command->a5 = value;
            break;
        case 6:
            command->a6 = value;
            break;
        case 7:
            command->a7 = value;
            break;
        case 8:
            command->a8 = value;
            break;
        default:
            command->a9 = value;
            break;
    }
}

uint32_t dr_parallel(void (*function)(int core, void* arg), void* arg) {
    return kmx_parallel(function, arg) == KMX_OK ? 0u : DR_PARALLEL;
}

void dr_sweep_start(dr_sweep_t* sweep, uint32_t region) {
    sweep->region = region;
    sweep->count = 0;
}

void dr_sweep_strided(
    dr_sweep_t* sweep, uint64_t at, uint64_t bytes, uint64_t stride, uint32_t repeats
) {
    if (sweep->count < DR_SWEEP_PARTS && bytes && repeats) {
        sweep->at[sweep->count] = at;
        sweep->bytes[sweep->count] = bytes;
        sweep->stride[sweep->count] = stride;
        sweep->repeats[sweep->count++] = repeats;
    }
}

void dr_sweep_add(dr_sweep_t* sweep, uint64_t at, uint64_t bytes) {
    dr_sweep_strided(sweep, at, bytes, 0, 1);
}

void dr_sweep_halves(dr_sweep_t* sweep, uint64_t at, uint64_t bytes) {
    const uint64_t half = (bytes / 2 + 63) & ~63ull;
    dr_sweep_add(sweep, at, half < bytes ? half : bytes);
    dr_sweep_add(sweep, at + half, half < bytes ? bytes - half : 0);
}

static void sweep_part(int core, void* arg) {
    const dr_sweep_t* sweep = (const dr_sweep_t*)arg;
    for (uint32_t part = (uint32_t)core; part < sweep->count; part += 4) {
        for (uint32_t repeat = 0; repeat < sweep->repeats[part]; repeat++) {
            kmx_invalidate_at(
                (int)sweep->region,
                sweep->at[part] + repeat * sweep->stride[part],
                sweep->bytes[part]
            );
        }
    }
}

uint32_t dr_sweep_run(dr_sweep_t* sweep) {
    return dr_parallel(sweep_part, sweep);
}

/* The numbers the frame reads: the cores, the bank, the layers. 0, or DR_BAD_ARGS. */
static uint32_t frame_numbers(dr_frame_t* frame) {
    dr_invalidate(DR_REGION_NUMBERS, 0, 4u * DR_NUMBER_WORDS);
    frame->cores = dr_number(frame, DR_N_CORES);
    frame->workers = dr_number(frame, DR_N_WORKERS);
    frame->bank_plus_one = 1 + dr_number(frame, DR_N_BANK);
    frame->layers = dr_number(frame, DR_N_LAYERS);
    if (frame->cores == 0 || frame->cores > frame->workers || frame->layers == 0 ||
        frame->layers > DR_LAYERS) {
        return DR_BAD_ARGS;
    }
    return 0;
}

/* The eye's view: a COLOUR view, its camera (and its address) and grid from the
 * numbers. 0, or DR_BAD_ARGS. */
static uint32_t eye_view(const dr_frame_t* frame, dr_view_t* view) {
    view->index = 0;
    view->kind = DR_VIEW_COLOUR;
    for (uint32_t i = 0; i < DR_N_CAMERA_WORDS; i++) {
        view->camera[i] = dr_number(frame, DR_N_CAMERA + i);
    }
    view->camera_at = dr_address(DR_REGION_NUMBERS, 4u * DR_N_CAMERA);
    view->target = view->target_first = view->target_across = view->target_pages = 0;
    view->transmit = view->transmit_base = view->transmit_channels = 0;
    view->grid = dr_number(frame, DR_N_GRID);
    view->tiles = dr_number(frame, DR_N_TILES);
    return view->tiles ? 0u : DR_BAD_ARGS;
}

uint64_t dr_row_start(dr_frame_t* frame) {
    for (uint32_t i = 0; i < DR_TIMES_WORDS; i++) {
        frame->times[i] = 0;
    }
    return kmx_time();
}

uint32_t dr_row_end(dr_frame_t* frame, uint32_t code, uint64_t started) {
    frame->times[DR_T_FRAME] = dr_ticks(&started);
    frame->times[DR_R_CODE] = code;
    frame->times[DR_R_NUMBER] = frame->served;
    frame->times[DR_R_RESUBMITS] = g_resubmits;
    frame->times[DR_R_WAKE_TICKS] = g_wake_ticks;
    const uint32_t at = 4u * DR_TIMES_WORDS * (frame->served % DR_TIMES_ROWS);
    uint32_t* row = (uint32_t*)dr_region(DR_REGION_TIMES, at);
    for (uint32_t i = 0; i < DR_TIMES_WORDS; i++) {
        row[i] = frame->times[i];
    }
    dr_flush(DR_REGION_TIMES, at, 4u * DR_TIMES_WORDS);
    frame->served++;
    return code;
}

uint32_t dr_ready(dr_frame_t* frame) {
    uint32_t code = frame->set_up ? frame->set_up : frame_numbers(frame);
    if (code == 0 && !g_ready) {
        code = dr_units_setup(frame);
        g_ready = code == 0;
    }
    return code;
}

uint32_t dr_serve_frame(dr_frame_t* frame) {
    uint32_t code = dr_ready(frame);
    const uint64_t started = dr_row_start(frame);
    dr_view_t view;
    if (code == 0) {
        code = eye_view(frame, &view);
    }
    if (code == 0) {
        dr_invalidate(DR_REGION_LAYERS, 0, 4u * DR_LAYER_WORDS * frame->layers);
        code = dr_view(frame, &view);
    }
    return dr_row_end(frame, code, started);
}

int kmx_main(int core) {
    (void)core;
    const kmx_args* arguments = kmx_args_get();
    dr_frame_t* frame = &g_frame;
    frame->set_up = arguments->nregions == DR_REGIONS ? 0u : DR_BAD_ARGS;
    for (uint32_t id = 0; id < DR_REGIONS && frame->set_up == 0; id++) {
        frame->regions[id] = kmx_region((int)id, &frame->bytes[id]);
        if (frame->regions[id] == 0 || arguments->region[id].offset >> 32) {
            frame->set_up = DR_BAD_ARGS;
        }
        frame->address[id] = (uint32_t)arguments->region[id].offset;
    }
    if (frame->set_up == 0) {
        frame->numbers = (const volatile uint32_t*)frame->regions[DR_REGION_NUMBERS];
    }
    return 0;
}
