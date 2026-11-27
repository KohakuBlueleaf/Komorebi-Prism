// A count range's box against the view (prism_reference.raster.cull.outside): wholly
// behind the near distance, or past an edge of the padded frame for every point in
// front of it. Float32 arithmetic on the streaming mover, once a range.
#pragma once

#include <stdint.h>

namespace geometry_k {

    constexpr uint32_t
        kBoxBytes = 64;              // a range's box page: least x, y, z, most x, y, z
    constexpr uint32_t kBoxAt = 64;  // the box's bytes in the camera's ring page
    constexpr uint32_t
        kCutWord = 32;  // the camera page's word: 1 when the range is cut
    constexpr float kBoxSlack = 1e-5f;  // cull.SLACK

    inline float cull_value(uint32_t pattern) {
        float number;
        __builtin_memcpy(&number, &pattern, 4);
        return number;
    }

    inline float cull_abs(float number) {
        return number < 0.0f ? -number : number;
    }

    // The most of a times a value in [low, high].
    inline float cull_most(float a, float low, float high) {
        return a >= 0.0f ? a * high : a * low;
    }

    // Whether the box (6 float32 words) lies outside the view of the camera's 16 words
    // for a padded frame of `across` x `down` tiles of 32.
    template <typename Words>
    inline bool box_outside(
        const Words& camera, const Words& box, uint32_t across, uint32_t down
    ) {
        float cam[16];
        for (uint32_t i = 0; i < 16; ++i) {
            cam[i] = cull_value(camera[i]);
        }
        float centre[3], size[3], d[3];
        for (uint32_t i = 0; i < 3; ++i) {
            const float least = cull_value(box[i]);
            const float most = cull_value(box[3 + i]);
            centre[i] = (least + most) * 0.5f;
            size[i] = (most - least) * 0.5f;
            d[i] = centre[i] - cam[i];
        }
        float scale = (cull_abs(d[0]) + cull_abs(d[1])) + cull_abs(d[2]);
        scale = scale + ((size[0] + size[1]) + size[2]);
        float low[3], high[3];
        for (uint32_t row = 0; row < 3; ++row) {
            const float* r = cam + 3 + 3 * row;
            const float at = (d[0] * r[0] + d[1] * r[1]) + d[2] * r[2];
            float reach = (size[0] * cull_abs(r[0]) + size[1] * cull_abs(r[1])) +
                size[2] * cull_abs(r[2]);
            reach = reach + scale * kBoxSlack;
            low[row] = at - reach;
            high[row] = at + reach;
        }
        const float focal = cam[12], cx = cam[13], cy = cam[14], near = cam[15];
        const float width = static_cast<float>(32u * across);
        const float height = static_cast<float>(32u * down);
        if (high[2] < near) {
            return true;
        }
        if (focal * high[0] + cull_most(cx, low[2], high[2]) < 0.0f) {
            return true;
        }
        if (-focal * low[0] + cull_most(width - cx, low[2], high[2]) < 0.0f) {
            return true;
        }
        if (cull_most(cy, low[2], high[2]) - focal * low[1] < 0.0f) {
            return true;
        }
        return focal * high[1] + cull_most(height - cy, low[2], high[2]) < 0.0f;
    }

}  // namespace geometry_k
