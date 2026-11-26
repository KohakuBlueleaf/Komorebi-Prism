/* The field update's parts over every core of the job thread and their math: the
 * arithmetic of indirect_field_update_parts.c, each part a share of the tiles, rows or
 * page lines whose writes lie in lines of its own. */

/* float32 as numpy: a product rounded before its sum (no fused multiply-add); zeroing
 * loops kept as loops (a memset call does not link) */
#pragma GCC optimize("fp-contract=off", "no-tree-loop-distribute-patterns")

#include "job_field.h"

#define ROWS_GRAIN 16u /* rows a share counts in: their values whole lines */
#define TEXELS_A_LINE (JB_LINE / 4u)

float jf_word_float(uint32_t word) {
    union {
        uint32_t u;
        float f;
    } both;

    both.u = word;
    return both.f;
}

uint32_t jf_float_word(float value) {
    union {
        uint32_t u;
        float f;
    } both;

    both.f = value;
    return both.u;
}

/* This part's view: the job's input and the regions as its cluster sees them. */
static void view_of(jf_view_t* view) {
    view->job = (const jf_job_t*)jb_input();
    view->elements = (const uint8_t*)jb_region(JB_REGION_FIELD_ELEMENTS, 0);
    view->shadow = (const float*)jb_region(JB_REGION_FIELD_SHADOW, 0);
    view->work = (uint8_t*)jb_region(JB_REGION_FIELD_WORK, 0);
    view->pages = (uint32_t*)jb_region(JB_REGION_FIELD_PAGES, 0);
}

/* Part `index`'s line of the job's block: its words, written back. */
static void give(uint32_t index, float top, uint32_t bad) {
    uint32_t* line = jb_given(index);
    line[JF_GIVEN_TOP] = jf_float_word(top);
    line[JF_GIVEN_BAD] = bad;
    jb_flush(JB_REGION_JOBS_BLOCK, JB_BLOCK_IN + JB_LINE * index, JB_LINE);
}

/* bfloat16 bits of a float32: nearest, ties to even (prism_reference bf16) */
static uint16_t bf16(float value) {
    const uint32_t bits = jf_float_word(value);
    return (uint16_t)((bits + 0x7FFFu + ((bits >> 16) & 1u)) >> 16);
}

/* A tile's element (row, column) of 32 x 32 in faces of 16 x 16 */
static uint32_t tile_at(uint32_t row, uint32_t column) {
    return (
        (row >> 4) * 512u + (column >> 4) * 256u + (row & 15u) * 16u + (column & 15u)
    );
}

static double square_root(double value) {
    double root;
    __asm__("fsqrt.d %0, %1" : "=f"(root) : "f"(value));
    return root;
}

/* round to nearest, ties to even (np.rint) */
static int64_t nearest(double value) {
    int64_t out;
    __asm__("fcvt.l.d %0, %1, rne" : "=r"(out) : "f"(value));
    return out;
}

/* np.floor of a float32 within +-2^31 as float32 */
static float floor_of(float value) {
    const int64_t whole = (int64_t)value;
    const float down = (float)whole;
    return down > value ? down - 1.0f : down;
}

/* 1 lit, 0 shadowed at texel (ix, iy) for 1/z `w` (outside the map lit) */
static float lit_at(const jf_view_t* view, int64_t ix, int64_t iy, float w) {
    const int64_t side = view->job->side;
    if (ix < 0 || ix >= side || iy < 0 || iy >= side) {
        return 1.0f;
    }
    const uint32_t x = (uint32_t)ix, y = (uint32_t)iy;
    const uint32_t page = (y >> 5) * (view->job->side >> 5) + (x >> 5);
    const float
        stored = (view->shadow[page * FU_PAGE_TEXELS + (y & 31u) * 32u + (x & 31u)]);
    return w < stored - view->job->bias ? 0.0f : 1.0f;
}

/* The sun's light at an element: sun_shadow (pcf) x max(n . s, 0). */
static float sun_light(
    const jf_view_t* view, const float* position, const float* normal
) {
    const jf_job_t* job = view->job;
    const float* camera = job->camera;
    const float q0 = position[0] + normal[0] * job->texel;
    const float q1 = position[1] + normal[1] * job->texel;
    const float q2 = position[2] + normal[2] * job->texel;
    const float d0 = q0 - camera[0], d1 = q1 - camera[1], d2 = q2 - camera[2];
    const float xc = (d0 * camera[3] + d1 * camera[4]) + d2 * camera[5];
    const float yc = (d0 * camera[6] + d1 * camera[7]) + d2 * camera[8];
    const float zc = (d0 * camera[9] + d1 * camera[10]) + d2 * camera[11];
    const float inv = 1.0f / zc;
    const float sx = camera[13] + camera[12] * (xc * inv);
    const float sy = camera[14] - camera[12] * (yc * inv);
    const float gx = sx - 0.5f, gy = sy - 0.5f;
    float shadow = 1.0f;
    /* far outside (or not a number): every texel outside the map, lit */
    if (gx > -2.0e9f && gx < 2.0e9f && gy > -2.0e9f && gy < 2.0e9f) {
        const float x0 = floor_of(gx), y0 = floor_of(gy);
        const float fx = gx - x0, fy = gy - y0;
        const int64_t ix = (int64_t)x0, iy = (int64_t)y0;
        const float top =
            (lit_at(view, ix, iy, inv) * (1.0f - fx) +
             lit_at(view, ix + 1, iy, inv) * fx);
        const float bottom =
            (lit_at(view, ix, iy + 1, inv) * (1.0f - fx) +
             lit_at(view, ix + 1, iy + 1, inv) * fx);
        shadow = top * (1.0f - fy) + bottom * fy;
    }
    const float facing =
        ((normal[0] * job->sun[0] + normal[1] * job->sun[1]) + normal[2] * job->sun[2]);
    return shadow * (facing > 0.0f ? facing : 0.0f);
}

static const float* element_array(const jf_view_t* view, uint32_t array) {
    return (const float*)(view->elements + view->job->element[array]);
}

static float* work_array(const jf_view_t* view, uint32_t array) {
    return (float*)(view->work + view->job->work[array]);
}

/* This part's tiles [first, end) of the job's. */
static void tiles_of(
    const jf_job_t* job, uint32_t index, uint32_t of, uint64_t* first, uint64_t* end
) {
    jb_share(index, of, job->tiles, 1, first, end);
}

/* The work array `array`'s bytes of tiles [first, end), `bytes` an element, written
 * back. */
static void flush_elements(
    const jf_view_t* view, uint32_t array, uint64_t first, uint64_t end, uint32_t bytes
) {
    const uint64_t at = view->job->work[array] + (uint64_t)bytes * FU_TILE * first;
    jb_flush(JB_REGION_FIELD_WORK, at, (uint64_t)bytes * FU_TILE * (end - first));
}

/* x's tiles [first, end) written back. */
static void flush_x(const jf_view_t* view, uint64_t first, uint64_t end) {
    const uint64_t at = view->job->work[JF_W_X] + (uint64_t)FU_X_PAGE_BYTES * first;
    jb_flush(JB_REGION_FIELD_WORK, at, (uint64_t)FU_X_PAGE_BYTES * (end - first));
}

void jf_sources_part(uint32_t index, uint32_t of) {
    jf_view_t view;
    view_of(&view);
    const jf_job_t* job = view.job;
    const float* position = element_array(&view, JF_E_POSITION);
    const float* normal = element_array(&view, JF_E_NORMAL);
    const float* base = element_array(&view, JF_E_BASE);
    const float* albedo = element_array(&view, JF_E_ALBEDO);
    const float* transfer = element_array(&view, JF_E_TRANSFER);
    float* sky = work_array(&view, JF_W_SKY);
    float* l0 = work_array(&view, JF_W_L0);
    float* total = work_array(&view, JF_W_TOTAL);
    uint16_t* x = (uint16_t*)(view.work + job->work[JF_W_X]);
    uint64_t first, end;
    tiles_of(job, index, of, &first, &end);
    for (uint32_t i = (uint32_t)first * FU_TILE; i < (uint32_t)end * FU_TILE; i++) {
        const float sun = sun_light(&view, position + 3 * i, normal + 3 * i);
        const float* row = transfer + FU_SKY_TERMS * i;
        uint16_t* tile = x + (i / FU_TILE) * (FU_X_PAGE_BYTES / 2);
        double sums[3] = {0.0, 0.0, 0.0}; /* each colour's in term order */
        for (uint32_t k = 0; k < FU_SKY_TERMS; k++) {
            sums[0] += (double)(row[k] * job->sky[3 * k]);
            sums[1] += (double)(row[k] * job->sky[3 * k + 1]);
            sums[2] += (double)(row[k] * job->sky[3 * k + 2]);
        }
        for (uint32_t c = 0; c < 3; c++) {
            const float s = (float)sums[c];
            const float clear = s > 0.0f ? s : 0.0f;
            const float light =
                (base[3 * i + c] +
                 albedo[3 * i + c] * (sun * job->irradiance[c] + clear));
            sky[3 * i + c] = clear;
            l0[3 * i + c] = light;
            total[3 * i + c] = 0.0f;
            tile[tile_at(c, i % FU_TILE)] = bf16(light);
        }
    }
    flush_elements(&view, JF_W_SKY, first, end, 12u);
    flush_elements(&view, JF_W_L0, first, end, 12u);
    flush_elements(&view, JF_W_TOTAL, first, end, 12u);
    flush_x(&view, first, end);
}

void jf_pass_part(uint32_t index, uint32_t of) {
    jf_view_t view;
    view_of(&view);
    const jf_job_t* job = view.job;
    const float* albedo = element_array(&view, JF_E_ALBEDO);
    float* total = work_array(&view, JF_W_TOTAL);
    const float* y = (const float*)(view.work + job->work[JF_W_Y]);
    uint16_t* x = (uint16_t*)(view.work + job->work[JF_W_X]);
    uint64_t first, end;
    tiles_of(job, index, of, &first, &end);
    for (uint32_t i = (uint32_t)first * FU_TILE; i < (uint32_t)end * FU_TILE; i++) {
        const float* tile = y + (i / FU_TILE) * (FU_Y_PAGE_BYTES / 4);
        uint16_t* out = x + (i / FU_TILE) * (FU_X_PAGE_BYTES / 2);
        for (uint32_t c = 0; c < 3; c++) {
            const float e = tile[tile_at(c, i % FU_TILE)];
            total[3 * i + c] = total[3 * i + c] + e;
            if (job->more) {
                out[tile_at(c, i % FU_TILE)] = bf16(albedo[3 * i + c] * e);
            }
        }
    }
    flush_elements(&view, JF_W_TOTAL, first, end, 12u);
    if (job->more) {
        flush_x(&view, first, end);
    }
}

void jf_source_part(uint32_t index, uint32_t of) {
    jf_view_t view;
    view_of(&view);
    const float* sky = work_array(&view, JF_W_SKY);
    float* total = work_array(&view, JF_W_TOTAL);
    uint64_t first, end;
    tiles_of(view.job, index, of, &first, &end);
    for (
        uint32_t i = 3u * FU_TILE * (uint32_t)first; i < 3u * FU_TILE * (uint32_t)end;
        i++
    ) {
        total[i] = total[i] + sky[i];
    }
    flush_elements(&view, JF_W_TOTAL, first, end, 12u);
}

void jf_rows_part(uint32_t index, uint32_t of) {
    jf_view_t view;
    view_of(&view);
    const jf_job_t* job = view.job;
    const float* e = work_array(&view, JF_W_TOTAL);
    float* values = work_array(&view, JF_W_VALUES);
    const uint32_t* starts = (const uint32_t*)(view.elements +
                                               job->element[JF_E_STARTS]);
    const uint32_t* pairs = (const uint32_t*)(view.elements + job->element[JF_E_PAIRS]);
    uint64_t first, end;
    jb_share(index, of, job->rows, ROWS_GRAIN, &first, &end);
    float top = 0.0f;
    uint32_t bad = 0;
    for (uint32_t r = (uint32_t)first; r < (uint32_t)end; r++) {
        const uint32_t from = starts[r];
        const uint32_t to = starts[r + 1] < job->weights ? starts[r + 1] : job->weights;
        double sum0 = 0.0, sum1 = 0.0, sum2 = 0.0;
        for (uint32_t j = from; j < to; j++) {
            const uint32_t column = pairs[2 * j];
            const float w = jf_word_float(pairs[2 * j + 1]);
            if (column >= job->n) {
                bad++;
                continue;
            }
            sum0 += (double)(w * e[3 * column]);
            sum1 += (double)(w * e[3 * column + 1]);
            sum2 += (double)(w * e[3 * column + 2]);
        }
        bad += from > to;
        const float v0 = (float)sum0, v1 = (float)sum1, v2 = (float)sum2;
        values[3 * r] = v0;
        values[3 * r + 1] = v1;
        values[3 * r + 2] = v2;
        top = v0 > top ? v0 : top;
        top = v1 > top ? v1 : top;
        top = v2 > top ? v2 : top;
    }
    jb_flush(
        JB_REGION_FIELD_WORK, job->work[JF_W_VALUES] + 12u * first, 12u * (end - first)
    );
    give(index, top, bad);
}

/* This part's lines of the field's pages, in texels [first, end). */
static void texels_of(
    const jf_job_t* job, uint32_t index, uint32_t of, uint64_t* first, uint64_t* end
) {
    const uint64_t texels = (uint64_t)job->pages_count * FU_PAGE_TEXELS;
    jb_share(index, of, texels, TEXELS_A_LINE, first, end);
}

void jf_zero_part(uint32_t index, uint32_t of) {
    jf_view_t view;
    view_of(&view);
    const jf_job_t* job = view.job;
    uint64_t first, end;
    texels_of(job, index, of, &first, &end);
    for (uint64_t i = first; i < end; i++) {
        view.pages[i] = 0;
    }
    jb_flush(JB_REGION_FIELD_PAGES, 4u * first, 4u * (end - first));
    uint64_t tile_first, tile_end;
    tiles_of(job, index, of, &tile_first, &tile_end);
    uint64_t* x = (uint64_t*)(view.work + job->work[JF_W_X]);
    const uint64_t words = FU_X_PAGE_BYTES / 8;
    for (uint64_t i = words * tile_first; i < words * tile_end; i++) {
        x[i] = 0;
    }
    flush_x(&view, tile_first, tile_end);
}

void jf_pack_part(uint32_t index, uint32_t of) {
    jf_view_t view;
    view_of(&view);
    const jf_job_t* job = view.job;
    const float* values = work_array(&view, JF_W_VALUES);
    const uint32_t* places = (const uint32_t*)(view.elements +
                                               job->element[JF_E_PLACES]);
    uint64_t first, end;
    texels_of(job, index, of, &first, &end);
    const uint32_t texels = job->pages_count * FU_PAGE_TEXELS;
    const double scale = (double)job->scale;
    static const uint32_t most[3] = {(1u << 11) - 1u, (1u << 11) - 1u, (1u << 9) - 1u};
    static const uint32_t shift[3] = {20u, 9u, 0u};
    uint32_t bad = 0;
    for (uint32_t r = 0; r < job->rows; r++) {
        const uint32_t place = places[r];
        const uint32_t at = place & 0x7FFFFFFFu;
        if (at >= texels) {
            bad += index == 0; /* counted once */
            continue;
        }
        if (at < first || at >= end) {
            continue;
        }
        uint32_t texel = 0;
        if (place >> 31) {
            texel = 0x80000000u;
            for (uint32_t c = 0; c < 3; c++) {
                const double v = (double)values[3 * r + c];
                int64_t code = 0;
                if (v > 0.0) {
                    code = nearest(square_root(v / scale) * (double)most[c]);
                }
                code = code < (int64_t)most[c] ? code : (int64_t)most[c];
                texel |= (uint32_t)code << shift[c];
            }
        }
        view.pages[at] = texel;
    }
    jb_flush(JB_REGION_FIELD_PAGES, 4u * first, 4u * (end - first));
    give(index, 0.0f, bad);
}
