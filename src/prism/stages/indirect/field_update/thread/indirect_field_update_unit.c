/* The field update's command `update`: its steps (the job taken, the sources, a pass,
 * the finish) and the step switch; each pass's apply by DR_GIVE_ELEMENTS_IRRADIANCE,
 * the copies by kmx_fetch and kmx_store, the times row into the unit's times region. */

/* float32 as numpy: a product rounded before its sum (no fused multiply-add); zeroing
 * loops kept as loops (a memset call does not link) */
#pragma GCC optimize("fp-contract=off", "no-tree-loop-distribute-patterns")

#include "indirect_field_update_unit.h"

_Static_assert(
    FU_TIMES_ROWS * FU_T_WORDS * 4u <=
        DR_INDIRECT_FIELD_UPDATE_REGION_FIELD_TIMES_BYTES,
    "the times rows in the times region"
);
_Static_assert(
    FU_T_PASS + FU_T_PASS_WORDS * FU_T_PASS_APART <= FU_T_ROWS,
    "the passes' words before the rows' word"
);

#define COPY_TICKS (4u * KMX_TICKS_PER_SECOND) /* a fetch's or a store's deadline */

/* What the steps of one update share (in .data: the image links no .bss). */
typedef struct {
    uint32_t state;   /* 0 nothing, 1 the sources done (x of pass 1 stored) */
    uint32_t bounces; /* the passes of this update (step 1's word) */
    uint32_t passes;  /* passes taken */
    uint32_t zeroed;  /* the pages and x's tiles zeroed (the first update) */
    uint32_t number;  /* updates finished */
    uint32_t times[FU_T_WORDS];
} update_t;

static update_t g_update __attribute__((section(".data"))) = {0, 0, 0, 0, 0, {1}};

/* The last finished update's scale word (in .data: the image links no .bss). */
static uint32_t g_scale __attribute__((section(".data"))) = 0;

static fu_job_t g_job __attribute__((section(".data"))) = {0};

/* Pass p's words of the times row: its own, or past FU_T_PASS_APART the last's. */
static uint32_t* pass_times(uint32_t p) {
    const uint32_t at = p < FU_T_PASS_APART ? p : FU_T_PASS_APART - 1u;
    return g_update.times + FU_T_PASS + FU_T_PASS_WORDS * at;
}

/* The regions, words and numbers of the update into `job`: 0, or FU_BAD_UPDATE when a
 * region does not hold what the words say. */
static uint32_t take_job(dr_frame_t* frame, fu_job_t* job) {
    if (frame->bytes[FU_R_HEADER] < FU_R_HEADER_AT + 4ull * FU_HEADER_WORDS) {
        return FU_BAD_UPDATE;
    }
    dr_invalidate(FU_R_HEADER, FU_R_HEADER_AT, 4u * FU_HEADER_WORDS);
    dr_invalidate(DR_REGION_NUMBERS, 0, 4u * DR_NUMBER_WORDS);
    const volatile uint32_t* header = (const volatile uint32_t*)DR_REGION(FU_R_HEADER);
    job->header = header;
    job->elements = (const uint8_t*)DR_REGION(FU_R_ELEMENTS);
    job->shadow = (const float*)DR_REGION(FU_R_SHADOW);
    job->work = (uint8_t*)DR_REGION(FU_R_WORK);
    job->pages = (uint32_t*)DR_REGION(FU_R_PAGES);
    job->cores = dr_number(frame, FU_N_CORES);
    job->shadow_at = dr_number(frame, FU_N_SHADOW);
    job->shadow_first = dr_number(frame, FU_N_SHADOW_FIRST);
    job->field_at = dr_number(frame, FU_N_FIELD);
    job->field_first = dr_number(frame, FU_N_FIELD_FIRST);
    job->x_at = dr_number(frame, FU_N_X);
    job->y_at = dr_number(frame, FU_N_Y);
    job->n = header[FU_H_N];
    job->tiles = header[FU_H_TILES];
    job->rows = header[FU_H_ROWS];
    job->weights = header[FU_H_WEIGHTS];
    job->pages_count = header[FU_H_PAGES];
    job->side = header[FU_H_SIDE];
    job->texel = fu_word_float(header[FU_H_TEXEL]);
    job->bias = fu_word_float(header[FU_H_BIAS]);
    for (uint32_t i = 0; i < 3; i++) {
        job->sun[i] = fu_word_float(header[FU_H_SUN + i]);
        job->irradiance[i] = fu_word_float(header[FU_H_IRRADIANCE + i]);
    }
    for (uint32_t i = 0; i < 16; i++) {
        job->camera[i] = fu_word_float(header[FU_H_CAMERA + i]);
    }
    for (uint32_t i = 0; i < FU_SKY_TERMS * 3; i++) {
        job->sky[i] = fu_word_float(header[FU_H_SKY + i]);
    }
    const uint64_t n = job->n, rows = job->rows;
    /* each array's end: (offset word, bytes) of the elements and work regions */
    const uint64_t elements_end[8][2] = {
        {header[FU_H_E_POSITION], 12 * n},
        {header[FU_H_E_NORMAL], 12 * n},
        {header[FU_H_E_BASE], 12 * n},
        {header[FU_H_E_ALBEDO], 12 * n},
        {header[FU_H_E_TRANSFER], 4 * FU_SKY_TERMS * n},
        {header[FU_H_E_STARTS], 4 * (rows + 1)},
        {header[FU_H_E_PAIRS], 8 * (uint64_t)job->weights},
        {header[FU_H_E_PLACES], 4 * rows},
    };
    const uint64_t work_end[6][2] = {
        {header[FU_H_W_SKY], 12 * n},
        {header[FU_H_W_L0], 12 * n},
        {header[FU_H_W_TOTAL], 12 * n},
        {header[FU_H_W_X], (uint64_t)FU_X_PAGE_BYTES * job->tiles},
        {header[FU_H_W_Y], (uint64_t)FU_Y_PAGE_BYTES * job->tiles},
        {header[FU_H_W_VALUES], 12 * rows},
    };
    const uint64_t shadow_bytes = (uint64_t)FU_PAGE_BYTES * header[FU_H_SHADOW_PAGES];
    uint32_t bad =
        (n == 0 || n != (uint64_t)FU_TILE * job->tiles || rows == 0 ||
         header[FU_H_X_PAGE] != FU_X_PAGE_BYTES ||
         header[FU_H_Y_PAGE] != FU_Y_PAGE_BYTES || job->cores == 0 || job->side == 0 ||
         job->side % 32u ||
         (uint64_t)job->side * job->side !=
             (uint64_t)FU_PAGE_TEXELS * header[FU_H_SHADOW_PAGES] ||
         frame->bytes[FU_R_SHADOW] < FU_R_SHADOW_AT + shadow_bytes ||
         frame->bytes[FU_R_PAGES] <
             FU_R_PAGES_AT + (uint64_t)FU_PAGE_BYTES * job->pages_count ||
         job->pages_count == 0 || job->pages_count >= (1u << 21));
    for (uint32_t i = 0; i < 8; i++) {
        bad |=
            (elements_end[i][0] % 4 != 0 ||
             FU_R_ELEMENTS_AT + elements_end[i][0] + elements_end[i][1] >
                 frame->bytes[FU_R_ELEMENTS]);
    }
    for (uint32_t i = 0; i < 6; i++) {
        bad |=
            (work_end[i][0] % 64 != 0 ||
             FU_R_WORK_AT + work_end[i][0] + work_end[i][1] > frame->bytes[FU_R_WORK]);
    }
    return bad ? FU_BAD_UPDATE : 0u;
}

/* x's tiles stored from the work region into x's tensor. 0, or FU_COPY. */
static uint32_t store_x(const fu_job_t* job) {
    kmx_event event;
    const kmx_dram x = {job->x_at, KM_COPY_INTERLEAVED, FU_X_PAGE_BYTES, 0u};
    return kmx_store(
               FU_R_WORK,
               FU_R_WORK_AT + job->header[FU_H_W_X],
               &x,
               (uint64_t)FU_X_PAGE_BYTES * job->tiles,
               0u,
               job->cores,
               kmx_time() + COPY_TICKS,
               &event
           ) == KMX_OK
        ? 0u
        : FU_COPY;
}

/* Step 1: the shadow map's pages fetched, the sources, x of pass 1 stored. */
static uint32_t sources(const dr_frame_t* frame, fu_job_t* job, uint64_t* mark) {
    const volatile uint32_t* header = job->header;
    update_t* update = &g_update;
    kmx_event event;
    if (!update->zeroed) {
        /* lines an earlier image left of the elements' arrays */
        dr_invalidate(
            FU_R_ELEMENTS,
            FU_R_ELEMENTS_AT,
            (uint32_t)(frame->bytes[FU_R_ELEMENTS] - FU_R_ELEMENTS_AT)
        );
    }
    const kmx_dram map = {
        job->shadow_at, KM_COPY_INTERLEAVED, FU_PAGE_BYTES, job->shadow_first
    };
    if (kmx_fetch(
            FU_R_SHADOW,
            FU_R_SHADOW_AT,
            &map,
            (uint64_t)FU_PAGE_BYTES * header[FU_H_SHADOW_PAGES],
            0u,
            job->cores,
            kmx_time() + COPY_TICKS,
            &event
        ) != KMX_OK) {
        return FU_COPY;
    }
    update->times[FU_T_FETCH] += dr_ticks(mark);
    if (!update->zeroed) {
        if (dr_parallel(fu_zero_part, job)) {
            return DR_PARALLEL;
        }
        update->zeroed = 1;
        update->times[FU_T_ZERO] += dr_ticks(mark);
    }
    if (dr_parallel(fu_sources_part, job)) {
        return DR_PARALLEL;
    }
    /* sky and L0 for the host's read after the stop */
    dr_flush(FU_R_WORK, FU_R_WORK_AT + header[FU_H_W_SKY], 12u * job->n);
    dr_flush(FU_R_WORK, FU_R_WORK_AT + header[FU_H_W_L0], 12u * job->n);
    update->times[FU_T_SOURCES] += dr_ticks(mark);
    update->state = 1;
    update->passes = 0;
    update->bounces = header[FU_H_BOUNCES];
    if (update->bounces == 0) {
        return 0;
    }
    if (store_x(job)) {
        return FU_COPY;
    }
    update->times[FU_T_PASS] += dr_ticks(mark);
    return 0;
}

/* Step 2: y fetched, added to the total; while passes remain, the next x stored. */
static uint32_t take_pass(fu_job_t* job, uint64_t* mark) {
    const volatile uint32_t* header = job->header;
    update_t* update = &g_update;
    if (update->state != 1 || update->passes >= update->bounces) {
        return FU_BAD_UPDATE;
    }
    uint32_t* times = pass_times(update->passes);
    kmx_event event;
    const kmx_dram y = {job->y_at, KM_COPY_INTERLEAVED, FU_Y_PAGE_BYTES, 0u};
    if (kmx_fetch(
            FU_R_WORK,
            FU_R_WORK_AT + header[FU_H_W_Y],
            &y,
            (uint64_t)FU_Y_PAGE_BYTES * job->tiles,
            0u,
            job->cores,
            kmx_time() + COPY_TICKS,
            &event
        ) != KMX_OK) {
        return FU_COPY;
    }
    times[2] += dr_ticks(mark);
    job->more = update->passes + 1 < update->bounces;
    if (dr_parallel(fu_pass_part, job)) {
        return DR_PARALLEL;
    }
    times[3] += dr_ticks(mark);
    update->passes++;
    if (!job->more) {
        return 0;
    }
    if (store_x(job)) {
        return FU_COPY;
    }
    pass_times(update->passes)[0] += dr_ticks(mark); /* the next pass's store */
    return 0;
}

/* Step 3: e, the rows, the scale, the texels, the pages stored. */
static uint32_t finish_update(fu_job_t* job, uint64_t* mark) {
    update_t* update = &g_update;
    if (update->state != 1 || update->passes != update->bounces) {
        return FU_BAD_UPDATE;
    }
    if (dr_parallel(fu_source_part, job) || dr_parallel(fu_rows_part, job)) {
        return DR_PARALLEL;
    }
    float top = 0.0f;
    uint32_t bad = 0;
    for (uint32_t i = 0; i < 4; i++) {
        top = job->top[i] > top ? job->top[i] : top;
        bad += job->bad[i];
    }
    job->scale = top > 0.0f ? top : 1.0f;
    update->times[FU_T_ROWS] += dr_ticks(mark);
    if (dr_parallel(fu_pack_part, job)) {
        return DR_PARALLEL;
    }
    for (uint32_t i = 0; i < 4; i++) {
        bad += job->bad[i];
    }
    update->times[FU_T_PACK] += dr_ticks(mark);
    if (bad) {
        return FU_BAD_UPDATE;
    }
    kmx_event event;
    const kmx_dram to = {
        job->field_at, KM_COPY_INTERLEAVED, FU_PAGE_BYTES, job->field_first
    };
    if (kmx_store(
            FU_R_PAGES,
            FU_R_PAGES_AT,
            &to,
            (uint64_t)FU_PAGE_BYTES * job->pages_count,
            0u,
            job->cores,
            kmx_time() + COPY_TICKS,
            &event
        ) != KMX_OK) {
        return FU_COPY;
    }
    update->times[FU_T_STORE] += dr_ticks(mark);
    /* LIGHT's unit a channel and the scale, for the unit that reads the field */
    static const uint32_t most[3] = {(1u << 11) - 1u, (1u << 11) - 1u, (1u << 9) - 1u};
    for (uint32_t c = 0; c < 3; c++) {
        const float unit = 1.0f / (float)most[c];
        update->times[FU_T_UNIT + c] = fu_float_word((unit * unit) * job->scale);
    }
    update->times[FU_T_SCALE] = fu_float_word(job->scale);
    g_scale = update->times[FU_T_SCALE];
    update->state = 0;
    update->number++;
    return 0;
}

/* The whole update: the sources, each pass's apply (the slot elements.irradiance's
 * giver) and its y, the finish. */
static uint32_t whole(dr_frame_t* frame, fu_job_t* job, uint64_t* mark) {
    update_t* update = &g_update;
    uint32_t code = sources(frame, job, mark);
    while (code == 0 && update->passes < update->bounces) {
        code = DR_GIVE_ELEMENTS_IRRADIANCE(frame);
        pass_times(update->passes)[1] += dr_ticks(mark);
        if (code == 0) {
            code = take_pass(job, mark);
        }
    }
    return code ? code : finish_update(job, mark);
}

/* This command's times row into the times region, row `number`. */
static void times_row(uint32_t number) {
    const uint32_t at = 4u * FU_T_WORDS * (number % FU_TIMES_ROWS);
    uint32_t* row = (uint32_t*)dr_region(FU_R_TIMES, FU_R_TIMES_AT + at);
    for (uint32_t i = 0; i < FU_T_WORDS; i++) {
        row[i] = g_update.times[i];
    }
    dr_flush(FU_R_TIMES, FU_R_TIMES_AT + at, 4u * FU_T_WORDS);
}

uint32_t indirect_field_update_unit_update(
    dr_frame_t* frame, const km_command_t* command
) {
    const uint64_t started = kmx_time();
    uint64_t mark = started;
    update_t* update = &g_update;
    fu_job_t* job = &g_job;
    const uint32_t step = command->a0;
    const uint32_t number = update->number; /* the update's row */
    uint32_t code = take_job(frame, job);
    if (code == 0 && (step == FU_STEP_ALL || step == FU_STEP_SOURCES)) {
        for (uint32_t i = 0; i < FU_T_WORDS; i++) {
            update->times[i] = 0;
        }
    }
    if (code == 0) {
        switch (step) {
            case FU_STEP_ALL:
                code = whole(frame, job, &mark);
                break;
            case FU_STEP_SOURCES:
                code = sources(frame, job, &mark);
                break;
            case FU_STEP_PASS:
                code = take_pass(job, &mark);
                break;
            case FU_STEP_FINISH:
                code = finish_update(job, &mark);
                break;
            default:
                code = FU_BAD_UPDATE;
        }
    }
    if (code) {
        update->state = 0;
    }
    update->times[FU_T_TOTAL] += (uint32_t)(kmx_time() - started);
    update->times[FU_T_NUMBER] = number;
    update->times[FU_T_CODE] = code;
    update->times[FU_T_STEP] = step;
    update->times[FU_T_PASSES] = update->passes;
    times_row(number);
    return code;
}

uint32_t indirect_field_update_unit_field_scale(
    dr_frame_t* frame, const km_command_t* command
) {
    (void)frame;
    (void)command;
    return g_scale;
}
