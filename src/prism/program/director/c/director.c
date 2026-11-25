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

uint32_t dr_submit(const km_command_t* command, uint32_t* handle) {
    const uint64_t until = kmx_time() + DR_WAIT_TICKS;
    int error = kmx_submit(command, handle);
    while (error == KMX_FULL && kmx_time() < until && !kmx_stop_requested()) {
        error = kmx_submit(command, handle);
    }
    return error == KMX_OK ? 0u : DR_RING;
}

uint32_t dr_wait(uint32_t handle) {
    kmx_event event;
    if (kmx_wait(handle, kmx_time() + DR_WAIT_TICKS, &event) != KMX_OK) {
        return DR_RING;
    }
    return event.kind == KM_EVENT_DONE ? 0u : DR_COMMAND;
}

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
