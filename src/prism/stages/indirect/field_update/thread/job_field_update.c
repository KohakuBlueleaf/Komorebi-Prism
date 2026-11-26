/* The field update's job commands on the job thread's lead: the job taken from the
 * header and numbers regions into the job's input, the sources, a pass, the finish,
 * the scale; the copies by Tensix cores, the regions dropped on every cluster before
 * the parts that read what another cluster or the cores wrote; the times row. */

/* zeroing loops kept as loops (a memset call does not link) */
#pragma GCC optimize("no-tree-loop-distribute-patterns")

#include "job_field.h"

_Static_assert(sizeof(jf_job_t) <= JB_INPUT_BYTES, "the job in the job's input");
_Static_assert(
    FU_TIMES_ROWS * FU_T_WORDS * 4u <= JB_REGION_FIELD_TIMES_BYTES,
    "the times rows in the times region"
);
_Static_assert(
    4u * FU_HEADER_WORDS <= JB_REGION_FIELD_HEADER_BYTES, "the header in its region"
);
_Static_assert(
    4u * JF_N_WORDS <= JB_REGION_FIELD_NUMBERS_BYTES, "the numbers in their region"
);
_Static_assert(
    FU_T_PASS + FU_T_PASS_WORDS * FU_T_PASS_APART <= FU_T_ROWS,
    "the passes' words before the rows' word"
);

/* What the steps of one update share (in .data: the image links no .bss). */
typedef struct {
    uint32_t state;   /* 0 nothing, 1 the sources done (x of pass 1 stored) */
    uint32_t bounces; /* the passes of this update (the header's at the sources) */
    uint32_t passes;  /* passes taken */
    uint32_t zeroed;  /* the pages and x's tiles zeroed (the first update) */
    uint32_t number;  /* updates finished */
    uint32_t times[FU_T_WORDS];
} update_t;

static update_t g_update __attribute__((section(".data"))) = {0, 0, 0, 0, 0, {1}};

/* The last finished update's scale word (in .data: the image links no .bss). */
static uint32_t g_scale __attribute__((section(".data"))) = 0;

/* The header's offset words of the arrays, in the order of jf_job_t's */
static const uint32_t k_element_words[JF_ELEMENT_ARRAYS] = {
    FU_H_E_POSITION,
    FU_H_E_NORMAL,
    FU_H_E_BASE,
    FU_H_E_ALBEDO,
    FU_H_E_TRANSFER,
    FU_H_E_STARTS,
    FU_H_E_PAIRS,
    FU_H_E_PLACES,
};
static const uint32_t k_work_words[JF_WORK_ARRAYS] = {
    FU_H_W_SKY,
    FU_H_W_L0,
    FU_H_W_TOTAL,
    FU_H_W_X,
    FU_H_W_Y,
    FU_H_W_VALUES,
};

static jf_job_t* job_input(void) {
    return (jf_job_t*)jb_input();
}

/* Pass p's words of the times row: its own, or past FU_T_PASS_APART the last's. */
static uint32_t* pass_times(uint32_t p) {
    const uint32_t at = p < FU_T_PASS_APART ? p : FU_T_PASS_APART - 1u;
    return g_update.times + FU_T_PASS + FU_T_PASS_WORDS * at;
}

/* Whether the arrays fit their regions, as the header's words say: 0, or
 * JF_BAD_UPDATE. */
static uint32_t check_arrays(const jf_job_t* job) {
    const uint64_t n = job->n, rows = job->rows;
    const uint64_t element_bytes[JF_ELEMENT_ARRAYS] = {
        12 * n,
        12 * n,
        12 * n,
        12 * n,
        4 * FU_SKY_TERMS * n,
        4 * (rows + 1),
        8 * (uint64_t)job->weights,
        4 * rows,
    };
    const uint64_t work_bytes[JF_WORK_ARRAYS] = {
        12 * n,
        12 * n,
        12 * n,
        (uint64_t)FU_X_PAGE_BYTES * job->tiles,
        (uint64_t)FU_Y_PAGE_BYTES * job->tiles,
        12 * rows,
    };
    uint32_t bad = 0;
    for (uint32_t i = 0; i < JF_ELEMENT_ARRAYS; i++) {
        bad |=
            (job->element[i] % 4 != 0 ||
             job->element[i] + element_bytes[i] >
                 jb_region_bytes(JB_REGION_FIELD_ELEMENTS));
    }
    for (uint32_t i = 0; i < JF_WORK_ARRAYS; i++) {
        bad |=
            (job->work[i] % JB_LINE != 0 ||
             job->work[i] + work_bytes[i] > jb_region_bytes(JB_REGION_FIELD_WORK));
    }
    return bad ? JF_BAD_UPDATE : 0u;
}

/* The header and numbers regions read afresh into the job's input: 0, or
 * JF_BAD_UPDATE when a region does not hold what the words say. */
static uint32_t take_job(jf_job_t* job) {
    jb_invalidate(JB_REGION_FIELD_HEADER, 0, 4u * FU_HEADER_WORDS);
    jb_invalidate(JB_REGION_FIELD_NUMBERS, 0, 4u * JF_N_WORDS);
    const volatile uint32_t* header = (const volatile uint32_t*)jb_region(
        JB_REGION_FIELD_HEADER, 0
    );
    const volatile uint32_t* numbers = (const volatile uint32_t*)jb_region(
        JB_REGION_FIELD_NUMBERS, 0
    );
    job->cores = numbers[JF_N_CORES];
    job->shadow_at = numbers[JF_N_SHADOW];
    job->shadow_first = numbers[JF_N_SHADOW_FIRST];
    job->field_at = numbers[JF_N_FIELD];
    job->field_first = numbers[JF_N_FIELD_FIRST];
    job->x_at = numbers[JF_N_X];
    job->y_at = numbers[JF_N_Y];
    job->n = header[FU_H_N];
    job->tiles = header[FU_H_TILES];
    job->rows = header[FU_H_ROWS];
    job->weights = header[FU_H_WEIGHTS];
    job->pages_count = header[FU_H_PAGES];
    job->side = header[FU_H_SIDE];
    job->shadow_pages = header[FU_H_SHADOW_PAGES];
    job->texel = jf_word_float(header[FU_H_TEXEL]);
    job->bias = jf_word_float(header[FU_H_BIAS]);
    for (uint32_t i = 0; i < 3; i++) {
        job->sun[i] = jf_word_float(header[FU_H_SUN + i]);
        job->irradiance[i] = jf_word_float(header[FU_H_IRRADIANCE + i]);
    }
    for (uint32_t i = 0; i < 16; i++) {
        job->camera[i] = jf_word_float(header[FU_H_CAMERA + i]);
    }
    for (uint32_t i = 0; i < FU_SKY_TERMS * 3; i++) {
        job->sky[i] = jf_word_float(header[FU_H_SKY + i]);
    }
    for (uint32_t i = 0; i < JF_ELEMENT_ARRAYS; i++) {
        job->element[i] = header[k_element_words[i]];
    }
    for (uint32_t i = 0; i < JF_WORK_ARRAYS; i++) {
        job->work[i] = header[k_work_words[i]];
    }
    const uint64_t shadow_bytes = (uint64_t)FU_PAGE_BYTES * job->shadow_pages;
    const uint32_t bad =
        (job->n == 0 || job->n != (uint64_t)FU_TILE * job->tiles || job->rows == 0 ||
         header[FU_H_X_PAGE] != FU_X_PAGE_BYTES ||
         header[FU_H_Y_PAGE] != FU_Y_PAGE_BYTES || job->cores == 0 || job->side == 0 ||
         job->side % 32u ||
         (uint64_t)job->side * job->side !=
             (uint64_t)FU_PAGE_TEXELS * job->shadow_pages ||
         jb_region_bytes(JB_REGION_FIELD_SHADOW) < shadow_bytes ||
         jb_region_bytes(JB_REGION_FIELD_PAGES) <
             (uint64_t)FU_PAGE_BYTES * job->pages_count ||
         job->pages_count == 0 || job->pages_count >= (1u << 21));
    return bad ? JF_BAD_UPDATE : check_arrays(job);
}

/* x's tiles stored from the work region into x's tensor. 0, or JF_COPY. */
static uint32_t store_x(const jf_job_t* job) {
    const kmx_dram x = {job->x_at, KM_COPY_INTERLEAVED, FU_X_PAGE_BYTES, 0u};
    return jb_store(
               JB_REGION_FIELD_WORK,
               job->work[JF_W_X],
               &x,
               (uint64_t)FU_X_PAGE_BYTES * job->tiles,
               0u,
               job->cores
           )
        ? JF_COPY
        : 0u;
}

/* `bytes` of the work array `array` dropped on every cluster: 0, or JB_PARALLEL. */
static uint32_t drop_work(const jf_job_t* job, uint32_t array, uint64_t bytes) {
    jb_drop_t drop;
    jb_drop_start(&drop);
    jb_drop_add(&drop, JB_REGION_FIELD_WORK, job->work[array], bytes);
    return jb_drop_run(&drop);
}

/* The sources: the shadow map fetched and dropped on every cluster (the elements too
 * the first time), the first update's zeroing, the sources' parts, pass 1's x stored.
 */
static uint32_t sources(jf_job_t* job, uint64_t* mark) {
    update_t* update = &g_update;
    const kmx_dram map = {
        job->shadow_at, KM_COPY_INTERLEAVED, FU_PAGE_BYTES, job->shadow_first
    };
    if (jb_fetch(
            JB_REGION_FIELD_SHADOW,
            0,
            &map,
            (uint64_t)FU_PAGE_BYTES * job->shadow_pages,
            0u,
            job->cores
        )) {
        return JF_COPY;
    }
    jb_drop_t drop;
    jb_drop_start(&drop);
    jb_drop_add(
        &drop, JB_REGION_FIELD_SHADOW, 0, (uint64_t)FU_PAGE_BYTES * job->shadow_pages
    );
    if (!update->zeroed) {
        /* lines an earlier image left of the elements' arrays */
        jb_drop_add(
            &drop,
            JB_REGION_FIELD_ELEMENTS,
            0,
            jb_region_bytes(JB_REGION_FIELD_ELEMENTS)
        );
    }
    if (jb_drop_run(&drop)) {
        return JB_PARALLEL;
    }
    update->times[FU_T_FETCH] += jb_ticks(mark);
    if (!update->zeroed) {
        if (jb_parallel(jf_zero_part)) {
            return JB_PARALLEL;
        }
        update->zeroed = 1;
        update->times[FU_T_ZERO] += jb_ticks(mark);
    }
    if (jb_parallel(jf_sources_part)) {
        return JB_PARALLEL;
    }
    update->times[FU_T_SOURCES] += jb_ticks(mark);
    update->state = 1;
    update->passes = 0;
    update->bounces = ((const volatile uint32_t*)jb_region(
        JB_REGION_FIELD_HEADER, 0
    ))[FU_H_BOUNCES];
    if (update->bounces == 0) {
        return 0;
    }
    if (store_x(job)) {
        return JF_COPY;
    }
    update->times[FU_T_PASS] += jb_ticks(mark);
    return 0;
}

/* A pass: y fetched and dropped on every cluster, added to the total; while passes
 * remain, the next x stored. */
static uint32_t take_pass(jf_job_t* job, uint64_t* mark) {
    update_t* update = &g_update;
    if (update->state != 1 || update->passes >= update->bounces) {
        return JF_BAD_UPDATE;
    }
    uint32_t* times = pass_times(update->passes);
    const kmx_dram y = {job->y_at, KM_COPY_INTERLEAVED, FU_Y_PAGE_BYTES, 0u};
    const uint64_t y_bytes = (uint64_t)FU_Y_PAGE_BYTES * job->tiles;
    if (jb_fetch(
            JB_REGION_FIELD_WORK, job->work[JF_W_Y], &y, y_bytes, 0u, job->cores
        )) {
        return JF_COPY;
    }
    if (drop_work(job, JF_W_Y, y_bytes)) {
        return JB_PARALLEL;
    }
    times[2] += jb_ticks(mark);
    job->more = update->passes + 1 < update->bounces;
    if (jb_parallel(jf_pass_part)) {
        return JB_PARALLEL;
    }
    times[3] += jb_ticks(mark);
    update->passes++;
    if (!job->more) {
        return 0;
    }
    if (store_x(job)) {
        return JF_COPY;
    }
    pass_times(update->passes)[0] += jb_ticks(mark); /* the next pass's store */
    return 0;
}

/* The parts' largest value and bad counts from their lines. */
static void given(float* top, uint32_t* bad) {
    for (uint32_t i = 0; i < jb_parts(); i++) {
        const uint32_t* line = jb_given(i);
        const float value = jf_word_float(line[JF_GIVEN_TOP]);
        *top = value > *top ? value : *top;
        *bad += line[JF_GIVEN_BAD];
    }
}

/* The finish: e, the total dropped on every cluster, the rows, the scale, the values
 * dropped, the texels, the pages stored. */
static uint32_t finish_update(jf_job_t* job, uint64_t* mark) {
    update_t* update = &g_update;
    if (update->state != 1 || update->passes != update->bounces) {
        return JF_BAD_UPDATE;
    }
    if (jb_parallel(jf_source_part) || drop_work(job, JF_W_TOTAL, 12ull * job->n) ||
        jb_parallel(jf_rows_part)) {
        return JB_PARALLEL;
    }
    float top = 0.0f;
    uint32_t bad = 0;
    given(&top, &bad);
    job->scale = top > 0.0f ? top : 1.0f;
    update->times[FU_T_ROWS] += jb_ticks(mark);
    if (drop_work(job, JF_W_VALUES, 12ull * job->rows) || jb_parallel(jf_pack_part)) {
        return JB_PARALLEL;
    }
    float unused = 0.0f;
    given(&unused, &bad);
    update->times[FU_T_PACK] += jb_ticks(mark);
    if (bad) {
        return JF_BAD_UPDATE;
    }
    const kmx_dram to = {
        job->field_at, KM_COPY_INTERLEAVED, FU_PAGE_BYTES, job->field_first
    };
    if (jb_store(
            JB_REGION_FIELD_PAGES,
            0,
            &to,
            (uint64_t)FU_PAGE_BYTES * job->pages_count,
            0u,
            job->cores
        )) {
        return JF_COPY;
    }
    update->times[FU_T_STORE] += jb_ticks(mark);
    /* LIGHT's unit a channel and the scale, for the record */
    static const uint32_t most[3] = {(1u << 11) - 1u, (1u << 11) - 1u, (1u << 9) - 1u};
    for (uint32_t c = 0; c < 3; c++) {
        const float unit = 1.0f / (float)most[c];
        update->times[FU_T_UNIT + c] = jf_float_word((unit * unit) * job->scale);
    }
    update->times[FU_T_SCALE] = jf_float_word(job->scale);
    g_scale = update->times[FU_T_SCALE];
    update->state = 0;
    update->number++;
    return 0;
}

/* This command's times row into the times region, row `number`. */
static void times_row(uint32_t number) {
    const uint32_t at = 4u * FU_T_WORDS * (number % FU_TIMES_ROWS);
    uint32_t* row = (uint32_t*)jb_region(JB_REGION_FIELD_TIMES, at);
    for (uint32_t i = 0; i < FU_T_WORDS; i++) {
        row[i] = g_update.times[i];
    }
    jb_flush(JB_REGION_FIELD_TIMES, at, 4u * FU_T_WORDS);
}

/* One step: the job taken, the step run, the times row written. */
static uint32_t step(uint32_t which) {
    const uint64_t started = kmx_time();
    uint64_t mark = started;
    update_t* update = &g_update;
    jf_job_t* job = job_input();
    const uint32_t number = update->number; /* the update's row */
    uint32_t code = take_job(job);
    if (code == 0 && which == FU_STEP_SOURCES) {
        for (uint32_t i = 0; i < FU_T_WORDS; i++) {
            update->times[i] = 0;
        }
    }
    if (code == 0) {
        switch (which) {
            case FU_STEP_SOURCES:
                code = sources(job, &mark);
                break;
            case FU_STEP_PASS:
                code = take_pass(job, &mark);
                break;
            default:
                code = finish_update(job, &mark);
                break;
        }
    }
    if (code) {
        update->state = 0;
    }
    update->times[FU_T_TOTAL] += (uint32_t)(kmx_time() - started);
    update->times[FU_T_NUMBER] = number;
    update->times[FU_T_CODE] = code;
    update->times[FU_T_STEP] = which;
    update->times[FU_T_PASSES] = update->passes;
    times_row(number);
    return code;
}

uint32_t job_field_sources(const km_command_t* command) {
    (void)command;
    return step(FU_STEP_SOURCES);
}

uint32_t job_field_pass(const km_command_t* command) {
    (void)command;
    return step(FU_STEP_PASS);
}

uint32_t job_field_finish(const km_command_t* command) {
    (void)command;
    return step(FU_STEP_FINISH);
}

uint32_t job_field_scale(const km_command_t* command) {
    (void)command;
    return g_scale;
}
