/* The field update's parts on the four cores and their math: the reference's arithmetic
 * (prism_reference.indirect: element_light to pack_field), each part a quarter. */

/* float32 as numpy: a product rounded before its sum (no fused multiply-add); zeroing
 * loops kept as loops (a memset call does not link) */
#pragma GCC optimize("fp-contract=off", "no-tree-loop-distribute-patterns")

#include "indirect_field_update_unit.h"

float fu_word_float(uint32_t word) {
    union {
        uint32_t u;
        float f;
    } both;

    both.u = word;
    return both.f;
}

uint32_t fu_float_word(float value) {
    union {
        uint32_t u;
        float f;
    } both;

    both.f = value;
    return both.u;
}

/* bfloat16 bits of a float32: nearest, ties to even (prism_reference bf16) */
static uint16_t bf16(float value) {
    const uint32_t bits = fu_float_word(value);
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

/* 1 lit, 0 shadowed at texel (ix, iy) for 1/z `w` (prism_reference.direct.shadow
 * sun_shadow's lit_at: outside the map lit) */
static float lit_at(const fu_job_t* job, int64_t ix, int64_t iy, float w) {
    const int64_t side = job->side;
    if (ix < 0 || ix >= side || iy < 0 || iy >= side) {
        return 1.0f;
    }
    const uint32_t x = (uint32_t)ix, y = (uint32_t)iy;
    const uint32_t page = (y >> 5) * (job->side >> 5) + (x >> 5);
    const float
        stored = (job->shadow[page * FU_PAGE_TEXELS + (y & 31u) * 32u + (x & 31u)]);
    return w < stored - job->bias ? 0.0f : 1.0f;
}

/* The sun's light at element i: sun_shadow (pcf) x max(n . s, 0). */
static float sun_light(
    const fu_job_t* job, const float* position, const float* normal
) {
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
            (lit_at(job, ix, iy, inv) * (1.0f - fx) +
             lit_at(job, ix + 1, iy, inv) * fx);
        const float bottom =
            (lit_at(job, ix, iy + 1, inv) * (1.0f - fx) +
             lit_at(job, ix + 1, iy + 1, inv) * fx);
        shadow = top * (1.0f - fy) + bottom * fy;
    }
    const float facing =
        ((normal[0] * job->sun[0] + normal[1] * job->sun[1]) + normal[2] * job->sun[2]);
    return shadow * (facing > 0.0f ? facing : 0.0f);
}

static const float* element_array(const fu_job_t* job, uint32_t word) {
    return (const float*)(job->elements + job->header[word]);
}

static float* work_array(const fu_job_t* job, uint32_t word) {
    return (float*)(job->work + job->header[word]);
}

/* Step 1's part: sky, sun, L0 of a quarter of the tiles; x of pass 1 (L0, bf16) into
 * x's tiles; the total 0. */
void fu_sources_part(int core, void* arg) {
    const fu_job_t* job = (const fu_job_t*)arg;
    const float* position = element_array(job, FU_H_E_POSITION);
    const float* normal = element_array(job, FU_H_E_NORMAL);
    const float* base = element_array(job, FU_H_E_BASE);
    const float* albedo = element_array(job, FU_H_E_ALBEDO);
    const float* transfer = element_array(job, FU_H_E_TRANSFER);
    float* sky = work_array(job, FU_H_W_SKY);
    float* l0 = work_array(job, FU_H_W_L0);
    float* total = work_array(job, FU_H_W_TOTAL);
    uint16_t* x = (uint16_t*)(job->work + job->header[FU_H_W_X]);
    const uint32_t quarter = (uint32_t)core;
    const uint32_t first = job->tiles * quarter / 4 * FU_TILE;
    const uint32_t end = job->tiles * (quarter + 1) / 4 * FU_TILE;
    for (uint32_t i = first; i < end; i++) {
        const float sun = sun_light(job, position + 3 * i, normal + 3 * i);
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
}

/* Step 2's part: E of the pass from y's tiles added to the total; with another pass,
 * its x = albedo / pi x E (bf16) into x's tiles. */
void fu_pass_part(int core, void* arg) {
    const fu_job_t* job = (const fu_job_t*)arg;
    const float* albedo = element_array(job, FU_H_E_ALBEDO);
    float* total = work_array(job, FU_H_W_TOTAL);
    const float* y = (const float*)(job->work + job->header[FU_H_W_Y]);
    uint16_t* x = (uint16_t*)(job->work + job->header[FU_H_W_X]);
    const uint32_t quarter = (uint32_t)core;
    const uint32_t first = job->tiles * quarter / 4 * FU_TILE;
    const uint32_t end = job->tiles * (quarter + 1) / 4 * FU_TILE;
    for (uint32_t i = first; i < end; i++) {
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
}

/* Step 3's first part: e = total + sky, in the total's place. */
void fu_source_part(int core, void* arg) {
    const fu_job_t* job = (const fu_job_t*)arg;
    const float* sky = work_array(job, FU_H_W_SKY);
    float* total = work_array(job, FU_H_W_TOTAL);
    const uint32_t quarter = (uint32_t)core;
    const uint32_t first = 3 * (job->n * quarter / 4);
    const uint32_t end = 3 * (job->n * (quarter + 1) / 4);
    for (uint32_t i = first; i < end; i++) {
        total[i] = total[i] + sky[i];
    }
}

/* Step 3's rows: v[r, c] = the row's sum of w x e[column, c] in its order (float32
 * products, a double sum), and the core's largest value. */
void fu_rows_part(int core, void* arg) {
    fu_job_t* job = (fu_job_t*)arg;
    const float* e = work_array(job, FU_H_W_TOTAL);
    float* values = work_array(job, FU_H_W_VALUES);
    const uint32_t* starts = ((const uint32_t*)(job->elements +
                                                job->header[FU_H_E_STARTS]));
    const uint32_t* pairs = ((const uint32_t*)(job->elements +
                                               job->header[FU_H_E_PAIRS]));
    const uint32_t quarter = (uint32_t)core;
    const uint32_t first = job->rows * quarter / 4;
    const uint32_t end = job->rows * (quarter + 1) / 4;
    float top = 0.0f;
    uint32_t bad = 0;
    for (uint32_t r = first; r < end; r++) {
        const uint32_t from = starts[r];
        const uint32_t to = starts[r + 1] < job->weights ? starts[r + 1] : job->weights;
        double sum0 = 0.0, sum1 = 0.0, sum2 = 0.0;
        for (uint32_t j = from; j < to; j++) {
            const uint32_t column = pairs[2 * j];
            const float w = fu_word_float(pairs[2 * j + 1]);
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
    job->top[quarter] = top;
    job->bad[quarter] = bad;
}

/* The pages' quarter zeroed (the first update): no voxel's texel is ever written in
 * the rest. */
void fu_zero_part(int core, void* arg) {
    fu_job_t* job = (fu_job_t*)arg;
    const uint32_t quarter = (uint32_t)core;
    const uint64_t words = (uint64_t)job->pages_count * (FU_PAGE_BYTES / 8);
    uint64_t* pages = (uint64_t*)job->pages;
    for (uint64_t i = words * quarter / 4; i < words * (quarter + 1) / 4; i++) {
        pages[i] = 0;
    }
    uint64_t* x = (uint64_t*)(job->work + job->header[FU_H_W_X]);
    const uint64_t x_words = (uint64_t)job->tiles * (FU_X_PAGE_BYTES / 8);
    for (uint64_t i = x_words * quarter / 4; i < x_words * (quarter + 1) / 4; i++) {
        x[i] = 0;
    }
}

/* Step 3's texels (indirect.pack_field): bit 31 where the row has data | each
 * channel's round(sqrt(v / scale) (2^bits - 1)) at its shift, into the row's place. */
void fu_pack_part(int core, void* arg) {
    fu_job_t* job = (fu_job_t*)arg;
    const float* values = work_array(job, FU_H_W_VALUES);
    const uint32_t* places = ((const uint32_t*)(job->elements +
                                                job->header[FU_H_E_PLACES]));
    const uint32_t quarter = (uint32_t)core;
    const uint32_t first = job->rows * quarter / 4;
    const uint32_t end = job->rows * (quarter + 1) / 4;
    const uint32_t texels = job->pages_count * FU_PAGE_TEXELS;
    const double scale = (double)job->scale;
    static const uint32_t most[3] = {(1u << 11) - 1u, (1u << 11) - 1u, (1u << 9) - 1u};
    static const uint32_t shift[3] = {20u, 9u, 0u};
    uint32_t bad = 0;
    for (uint32_t r = first; r < end; r++) {
        const uint32_t place = places[r];
        const uint32_t at = place & 0x7FFFFFFFu;
        if (at >= texels) {
            bad++;
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
        job->pages[at] = texel;
    }
    job->bad[quarter] += bad;
}
