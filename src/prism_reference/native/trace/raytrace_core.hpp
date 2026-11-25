// Tree walk, triangle test and shading of prism_reference.trace.tracer: float32 only,
// no fused multiply-add (build with -ffp-contract=off), one ray with a stack.
#pragma once

#include <cmath>
#include <cstdint>

#include "kr.hpp"

namespace kr {

    constexpr uint32_t LEAF_BIT = 0x80000000u;
    constexpr int STACK = 64;
    constexpr float TMAX = 1e30f;
    constexpr float SLAB_SCALE = 1.0000004f;
    constexpr float MIN_DIR = 1e-12f;
    constexpr float AMBIENT = 0.1f;
    constexpr float GI = 0.5f;
    constexpr uint32_t BOUNCE_SEED = 7;

    struct Tree {
        const uint32_t* nodes;    // (M, 8): box min, box max, child 0, child 1
        const float* tris;        // (N, 9) in leaf order: v0, e1, e2
        const int32_t* leaf_tri;  // leaf -> triangle index of the scene
    };

    struct Scene {
        Tree tree;
        const float* colors;
        const int32_t* indices;
        float camera[16];
        float light[3];
        float eps;
    };

    struct Ray {
        float origin[3], direction[3], inverse[3];
    };

    struct Hit {
        float t, u, v;
        int32_t leaf;    // -1: none
        int32_t nodes;   // box tests
        int32_t leaves;  // triangle tests
    };

    // Per-pixel buffers of one frame (pointers, so the same code runs on host and
    // device).
    struct Frame {
        Hit *hit0, *hit1;
        float *normal, *origin, *albedo, *direct0, *bounce_directions, *radiance1,
            *colour;
    };

    KR_HD inline float dot3(const float* left, const float* right) {
        return (left[0] * right[0] + left[1] * right[1]) + left[2] * right[2];
    }

    KR_HD inline void cross3(const float* left, const float* right, float* result) {
        result[0] = left[1] * right[2] - left[2] * right[1];
        result[1] = left[2] * right[0] - left[0] * right[2];
        result[2] = left[0] * right[1] - left[1] * right[0];
    }

    KR_HD inline void make_ray(Ray& ray, const float* origin, const float* direction) {
        for (int axis = 0; axis < 3; axis++) {
            ray.origin[axis] = origin[axis];
            ray.direction[axis] = direction[axis];
            float safe =
                (fabsf(direction[axis]) < MIN_DIR ? copysignf(MIN_DIR, direction[axis])
                                                  : direction[axis]);
            ray.inverse[axis] = 1.0f / safe;
        }
    }

    KR_HD inline float as_float(uint32_t word) {
        union {
            uint32_t bits;
            float value;
        } converter;

        converter.bits = word;
        return converter.value;
    }

    // Box of a node against the ray: true when hit, with the entry distance.
    KR_HD inline bool box_test(
        const uint32_t* node, const Ray& ray, float best, float& entry
    ) {
        float near_[3], far_[3];
        for (int axis = 0; axis < 3; axis++) {
            float to_low =
                ((as_float(node[axis]) - ray.origin[axis]) * ray.inverse[axis]);
            float to_high =
                ((as_float(node[3 + axis]) - ray.origin[axis]) * ray.inverse[axis]);
            near_[axis] = to_low < to_high ? to_low : to_high;
            far_[axis] = to_low < to_high ? to_high : to_low;
        }
        float near_xy = near_[0] > near_[1] ? near_[0] : near_[1];
        float near_z = near_[2] > 0.0f ? near_[2] : 0.0f;
        entry = near_xy > near_z ? near_xy : near_z;
        float far_xy = far_[0] < far_[1] ? far_[0] : far_[1];
        float exit_ = (far_xy < far_[2] ? far_xy : far_[2]) * SLAB_SCALE;
        return entry <= (exit_ < best ? exit_ : best);
    }

    KR_HD inline bool triangle_test(
        const float* triangle, const Ray& ray, float& t, float& u, float& v
    ) {
        float p_vector[3], t_vector[3], q_vector[3];
        cross3(ray.direction, triangle + 6, p_vector);
        float determinant = dot3(triangle + 3, p_vector);
        if (determinant == 0.0f) {
            return false;
        }
        float inverse_determinant = 1.0f / determinant;
        for (int axis = 0; axis < 3; axis++) {
            t_vector[axis] = ray.origin[axis] - triangle[axis];
        }
        u = dot3(t_vector, p_vector) * inverse_determinant;
        if (!(u >= 0.0f && u <= 1.0f)) {
            return false;
        }
        cross3(t_vector, triangle + 3, q_vector);
        v = dot3(ray.direction, q_vector) * inverse_determinant;
        if (!(v >= 0.0f && u + v <= 1.0f)) {
            return false;
        }
        t = dot3(triangle + 6, q_vector) * inverse_determinant;
        return t > 0.0f;
    }

    // Closest hit with t < tmax (any_hit: stops at the first hit; best stays tmax).
    KR_HD inline void trace(
        const Tree& tree, const Ray& ray, float tmax, bool any_hit, Hit& hit
    ) {
        hit.t = tmax;
        hit.u = hit.v = 0.0f;
        hit.leaf = -1;
        hit.nodes = 1;
        hit.leaves = 0;
        float best = tmax, entry;
        int32_t stack_node[STACK];
        float stack_t[STACK];
        if (!box_test(tree.nodes, ray, best, entry)) {
            return;
        }
        stack_node[0] = 0;
        stack_t[0] = entry;
        int stack_size = 1;
        while (stack_size > 0) {
            stack_size--;
            if (!(stack_t[stack_size] <= best)) {
                continue;
            }
            const uint32_t* node = tree.nodes + 8 * (size_t)stack_node[stack_size];
            if (node[6] & LEAF_BIT) {
                int leaf = (int)(node[6] & ~LEAF_BIT);
                float t, u, v;
                hit.leaves++;
                if (!triangle_test(tree.tris + 9 * (size_t)leaf, ray, t, u, v)) {
                    continue;
                }
                bool better = t < best;
                if (!any_hit && !better && t == best && hit.leaf >= 0) {
                    better = tree.leaf_tri[leaf] < tree.leaf_tri[hit.leaf];
                }
                if (better) {
                    hit.t = t;
                    hit.u = u;
                    hit.v = v;
                    hit.leaf = leaf;
                    if (any_hit) {
                        return;
                    }
                    best = t;
                }
                continue;
            }
            float first_entry, second_entry;
            bool first_hit = (box_test(
                tree.nodes + 8 * (size_t)node[6], ray, best, first_entry
            ));
            bool second_hit = (box_test(
                tree.nodes + 8 * (size_t)node[7], ray, best, second_entry
            ));
            hit.nodes += 2;
            if (first_hit && second_hit) {
                bool second_nearer = second_entry < first_entry;
                stack_node[stack_size] = (int32_t)(second_nearer ? node[6] : node[7]);
                stack_t[stack_size++] = second_nearer ? first_entry : second_entry;
                stack_node[stack_size] = (int32_t)(second_nearer ? node[7] : node[6]);
                stack_t[stack_size++] = second_nearer ? second_entry : first_entry;
            } else if (first_hit || second_hit) {
                stack_node[stack_size] = (int32_t)(first_hit ? node[6] : node[7]);
                stack_t[stack_size++] = first_hit ? first_entry : second_entry;
            }
        }
    }

    KR_HD inline void camera_ray(const float* camera, int pixel, Ray& ray) {
        float x = (float)(pixel % WIDTH) + 0.5f;
        float y = (float)(pixel / WIDTH) + 0.5f;
        float screen_x = (x - camera[13]) / camera[12];
        float screen_y = (y - camera[14]) / camera[12];
        float direction[3];
        for (int axis = 0; axis < 3; axis++) {
            direction[axis] =
                ((camera[9 + axis] + camera[3 + axis] * screen_x) -
                 camera[6 + axis] * screen_y);
        }
        make_ray(ray, camera, direction);
    }

    KR_HD inline void sky(const float* direction, float* colour) {
        float height = direction[1] / sqrtf(dot3(direction, direction));
        height = fminf(fmaxf(height, 0.0f), 1.0f);
        const float horizon[3] = {0.85f, 0.88f, 0.95f};
        const float zenith[3] = {0.35f, 0.55f, 0.9f};
        for (int axis = 0; axis < 3; axis++) {
            colour[axis] = horizon[axis] + (zenith[axis] - horizon[axis]) * height;
        }
    }

    // Normal facing against the ray direction, and the colour interpolated at a hit.
    KR_HD inline void surface(
        const Scene& scene,
        const Hit& hit,
        const float* direction,
        float* normal,
        float* albedo
    ) {
        const float* triangle = scene.tree.tris + 9 * (size_t)hit.leaf;
        cross3(triangle + 3, triangle + 6, normal);
        float length = sqrtf(dot3(normal, normal));
        for (int axis = 0; axis < 3; axis++) {
            normal[axis] = normal[axis] / length;
        }
        if (dot3(normal, direction) > 0.0f) {
            for (int axis = 0; axis < 3; axis++) {
                normal[axis] = -normal[axis];
            }
        }
        const int32_t*
            corners = (scene.indices + 3 * (size_t)scene.tree.leaf_tri[hit.leaf]);
        float weight1 = hit.u, weight2 = hit.v, weight0 = (1.0f - weight1) - weight2;
        for (int axis = 0; axis < 3; axis++) {
            albedo[axis] =
                ((scene.colors[3 * corners[0] + axis] * weight0 +
                  scene.colors[3 * corners[1] + axis] * weight1) +
                 scene.colors[3 * corners[2] + axis] * weight2);
        }
    }

    // The point `offset` above the surface at `point`, along the normal.
    KR_HD inline void offset_point(
        const Scene& scene, const float* point, const float* normal, float* offset
    ) {
        for (int axis = 0; axis < 3; axis++) {
            offset[axis] = point[axis] + normal[axis] * scene.eps;
        }
    }

    // The shadow ray from origin: direction light - origin, t in (0, 1); cosine is
    // normal . to_light / |to_light|.
    KR_HD inline void shadow_ray(
        const Scene& scene,
        const float* origin,
        const float* normal,
        Ray& ray,
        float& cosine
    ) {
        float to_light[3];
        for (int axis = 0; axis < 3; axis++) {
            to_light[axis] = scene.light[axis] - origin[axis];
        }
        cosine = dot3(normal, to_light) * (1.0f / sqrtf(dot3(to_light, to_light)));
        make_ray(ray, origin, to_light);
    }

    KR_HD inline float diffuse(float cosine, bool occluded) {
        return occluded ? 0.0f : (cosine > 0.0f ? cosine : 0.0f);
    }

    // A unit direction along the normal plus a random unit vector, from the hash of the
    // pixel.
    KR_HD inline void bounce_direction(int pixel, const float* normal, float* bounce) {
        float random_vector[3];
        for (int axis = 0; axis < 3; axis++) {
            float uniform0 = uniform(pixel, 4 * axis + 0, BOUNCE_SEED);
            float uniform1 = uniform(pixel, 4 * axis + 1, BOUNCE_SEED);
            float uniform2 = uniform(pixel, 4 * axis + 2, BOUNCE_SEED);
            float uniform3 = uniform(pixel, 4 * axis + 3, BOUNCE_SEED);
            random_vector
                [axis] = ((((uniform0 + uniform1) + uniform2) + uniform3) - 2.0f);
        }
        float squared_length = dot3(random_vector, random_vector);
        float unit_random[3];
        for (int axis = 0; axis < 3; axis++) {
            unit_random[axis] =
                (squared_length < 1e-12f ? normal[axis]
                                         : random_vector[axis] /
                         sqrtf(squared_length > 1e-12f ? squared_length : 1e-12f));
        }
        float sum[3] = {
            normal[0] + unit_random[0],
            normal[1] + unit_random[1],
            normal[2] + unit_random[2]
        };
        float squared_sum = dot3(sum, sum);
        for (int axis = 0; axis < 3; axis++) {
            bounce[axis] =
                (squared_sum < 1e-6f
                     ? normal[axis]
                     : sum[axis] / sqrtf(squared_sum > 1e-6f ? squared_sum : 1e-6f));
        }
    }

    // The five stages of one pixel.
    KR_HD inline void primary_ray(const Scene& scene, const Frame& frame, int pixel) {
        Ray ray;
        camera_ray(scene.camera, pixel, ray);
        trace(scene.tree, ray, TMAX, false, frame.hit0[pixel]);
    }

    // Normal, colour, offset origin and the shadow ray's diffuse term at the primary
    // hit.
    KR_HD inline void shadow_primary(
        const Scene& scene, const Frame& frame, int pixel
    ) {
        const Hit& hit = frame.hit0[pixel];
        if (hit.leaf < 0) {
            return;
        }
        Ray ray;
        camera_ray(scene.camera, pixel, ray);
        float point[3];
        for (int axis = 0; axis < 3; axis++) {
            point[axis] = ray.origin[axis] + ray.direction[axis] * hit.t;
        }
        float* normal = &frame.normal[3 * pixel];
        surface(scene, hit, ray.direction, normal, &frame.albedo[3 * pixel]);
        float* shadow_origin = &frame.origin[3 * pixel];
        offset_point(scene, point, normal, shadow_origin);
        Ray shadow;
        float cosine;
        shadow_ray(scene, shadow_origin, normal, shadow, cosine);
        Hit shadow_hit;
        trace(scene.tree, shadow, 1.0f, true, shadow_hit);
        frame.direct0[pixel] = diffuse(cosine, shadow_hit.leaf >= 0);
    }

    KR_HD inline void bounce_ray(const Scene& scene, const Frame& frame, int pixel) {
        if (frame.hit0[pixel].leaf < 0) {
            return;
        }
        float* direction = &frame.bounce_directions[3 * pixel];
        bounce_direction(pixel, &frame.normal[3 * pixel], direction);
        Ray ray;
        make_ray(ray, &frame.origin[3 * pixel], direction);
        trace(scene.tree, ray, TMAX, false, frame.hit1[pixel]);
    }

    KR_HD inline void shadow_bounce(const Scene& scene, const Frame& frame, int pixel) {
        if (frame.hit0[pixel].leaf < 0) {
            return;
        }
        const float* direction = &frame.bounce_directions[3 * pixel];
        float* radiance = &frame.radiance1[3 * pixel];
        const Hit& hit = frame.hit1[pixel];
        if (hit.leaf < 0) {
            sky(direction, radiance);
            return;
        }
        const float* shadow_origin = &frame.origin[3 * pixel];
        float point[3], normal[3], albedo[3];
        for (int axis = 0; axis < 3; axis++) {
            point[axis] = shadow_origin[axis] + direction[axis] * hit.t;
        }
        surface(scene, hit, direction, normal, albedo);
        float bounce_shadow_origin[3];
        offset_point(scene, point, normal, bounce_shadow_origin);
        Ray shadow;
        float cosine;
        shadow_ray(scene, bounce_shadow_origin, normal, shadow, cosine);
        Hit shadow_hit;
        trace(scene.tree, shadow, 1.0f, true, shadow_hit);
        float direct = diffuse(cosine, shadow_hit.leaf >= 0);
        for (int axis = 0; axis < 3; axis++) {
            radiance[axis] = albedo[axis] * (AMBIENT + direct);
        }
    }

    KR_HD inline void shade(const Scene& scene, const Frame& frame, int pixel) {
        float* colour = &frame.colour[3 * pixel];
        if (frame.hit0[pixel].leaf < 0) {
            Ray ray;
            camera_ray(scene.camera, pixel, ray);
            sky(ray.direction, colour);
            return;
        }
        for (int axis = 0; axis < 3; axis++) {
            colour[axis] =
                (frame.albedo[3 * pixel + axis] *
                 ((AMBIENT + frame.direct0[pixel]) +
                  GI * frame.radiance1[3 * pixel + axis]));
        }
    }

}  // namespace kr
