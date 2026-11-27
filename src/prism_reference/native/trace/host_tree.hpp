// The host's own box tree over the reference tree's triangles: binned surface-area
// cuts, leaves of a few triangles, both children's boxes in one node, depth-first
// order; the walk with raytrace_core.hpp's triangle test.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <future>
#include <vector>

#include "raytrace_core.hpp"

namespace host {

    constexpr int BINS = 16;
    constexpr int STACK = 64;
    constexpr float TRAVERSE = 1.0f;  // a node's cost against a triangle's
    constexpr float INTERSECT = 1.0f;
    constexpr int PARALLEL_FROM = 1 << 16;  // triangles a branch must hold to fork

    struct Box {
        float low[3], high[3];

        void reset() {
            for (int a = 0; a < 3; a++) {
                low[a] = INFINITY;
                high[a] = -INFINITY;
            }
        }

        void grow(const Box& other) {
            for (int a = 0; a < 3; a++) {
                low[a] = std::min(low[a], other.low[a]);
                high[a] = std::max(high[a], other.high[a]);
            }
        }

        void grow(const float* point) {
            for (int a = 0; a < 3; a++) {
                low[a] = std::min(low[a], point[a]);
                high[a] = std::max(high[a], point[a]);
            }
        }

        float area() const {
            float d[3];
            for (int a = 0; a < 3; a++) {
                d[a] = std::max(high[a] - low[a], 0.0f);
            }
            return 2.0f * (d[0] * d[1] + d[1] * d[2] + d[2] * d[0]);
        }
    };

    // An inner node holds both children's boxes; a child is a node (count 0) or a
    // leaf (count triangles from first).
    struct Node {
        float low[2][3], high[2][3];
        uint32_t first[2], count[2];
    };

    struct Tree {
        std::vector<Node> nodes;
        std::vector<float> tris;     // (n, 9) v0, e1, e2 in this tree's order
        std::vector<int32_t> leaf;   // the reference tree's leaf of each triangle
        std::vector<int32_t> scene;  // the scene's triangle of each (ties)
        Box root;
        uint32_t root_count = 0;  // the root as a child: 0 node 0, else a leaf
    };

    struct Builder {
        const float* tris;
        std::vector<Box> boxes;
        std::vector<float> centre;
        std::vector<uint32_t> order;
        int leaf_most;
        bool median;
    };

    struct Part {
        Box box;
        uint32_t first, count;
        // filled by build: the child word of this part
        std::vector<Node> nodes;  // the subtree's nodes, its root at 0
    };

    // The cut of order[first, first + count): its left count (0: a leaf).
    inline uint32_t cut(Builder& b, uint32_t first, uint32_t count, const Box& box) {
        if (count <= 1) {
            return 0;
        }
        Box centres;
        centres.reset();
        for (uint32_t i = first; i < first + count; i++) {
            centres.grow(&b.centre[3 * b.order[i]]);
        }
        int axis = 0;
        float extent = -1.0f;
        for (int a = 0; a < 3; a++) {
            float e = centres.high[a] - centres.low[a];
            if (e > extent) {
                extent = e;
                axis = a;
            }
        }
        uint32_t* items = b.order.data() + first;
        if (b.median || extent <= 0.0f) {
            if (count <= (uint32_t)b.leaf_most) {
                return 0;
            }
            uint32_t half = count / 2;
            std::nth_element(
                items, items + half, items + count, [&](uint32_t l, uint32_t r) {
                    return b.centre[3 * l + axis] < b.centre[3 * r + axis];
                }
            );
            return half;
        }
        float best = INFINITY;
        int best_axis = -1, best_plane = 0;
        for (int a = 0; a < 3; a++) {
            float low = centres.low[a], e = centres.high[a] - low;
            if (e <= 0.0f) {
                continue;
            }
            Box bins[BINS];
            uint32_t counts[BINS] = {};
            for (auto& one : bins) {
                one.reset();
            }
            float scale = BINS / e;
            for (uint32_t i = 0; i < count; i++) {
                uint32_t t = items[i];
                int k = std::min(BINS - 1, (int)((b.centre[3 * t + a] - low) * scale));
                counts[k]++;
                bins[k].grow(b.boxes[t]);
            }
            float right_area[BINS];
            uint32_t right_count[BINS];
            Box acc;
            acc.reset();
            uint32_t n = 0;
            for (int k = BINS - 1; k > 0; k--) {
                acc.grow(bins[k]);
                n += counts[k];
                right_area[k] = acc.area();
                right_count[k] = n;
            }
            acc.reset();
            n = 0;
            for (int k = 0; k < BINS - 1; k++) {
                acc.grow(bins[k]);
                n += counts[k];
                if (n == 0 || right_count[k + 1] == 0) {
                    continue;
                }
                float cost = n * acc.area() + right_count[k + 1] * right_area[k + 1];
                if (cost < best) {
                    best = cost;
                    best_axis = a;
                    best_plane = k;
                }
            }
        }
        float leaf_cost = INTERSECT * count;
        float split_cost = TRAVERSE + INTERSECT * best / box.area();
        if (best_axis < 0) {
            if (count <= (uint32_t)b.leaf_most) {
                return 0;
            }
            return count / 2;
        }
        if (count <= (uint32_t)b.leaf_most && leaf_cost <= split_cost) {
            return 0;
        }
        float low = centres.low[best_axis];
        float scale = BINS / (centres.high[best_axis] - low);
        uint32_t* middle = std::partition(items, items + count, [&](uint32_t t) {
            int k = std::min(
                BINS - 1, (int)((b.centre[3 * t + best_axis] - low) * scale)
            );
            return k <= best_plane;
        });
        return (uint32_t)(middle - items);
    }

    inline Box bounds(const Builder& b, uint32_t first, uint32_t count) {
        Box box;
        box.reset();
        for (uint32_t i = first; i < first + count; i++) {
            box.grow(b.boxes[b.order[i]]);
        }
        return box;
    }

    // The subtree over order[first, first + count) appended to `nodes`, depth first;
    // its child word (first, count) for the parent.
    inline void subtree(
        Builder& b,
        uint32_t first,
        uint32_t count,
        const Box& box,
        std::vector<Node>& nodes,
        uint32_t& word_first,
        uint32_t& word_count,
        int depth,
        int fork_depth
    ) {
        uint32_t left = cut(b, first, count, box);
        if (left == 0 || depth >= STACK - 2) {
            word_first = first;
            word_count = count;
            return;
        }
        uint32_t at = (uint32_t)nodes.size();
        nodes.emplace_back();
        word_first = at;
        word_count = 0;
        Box boxes[2] = {bounds(b, first, left), bounds(b, first + left, count - left)};
        uint32_t starts[2] = {first, first + left}, counts[2] = {left, count - left};
        uint32_t child_first[2], child_count[2];
        if (depth < fork_depth && count >= (uint32_t)PARALLEL_FROM) {
            std::vector<Node> other;
            auto right = std::async(std::launch::async, [&]() {
                subtree(
                    b,
                    starts[1],
                    counts[1],
                    boxes[1],
                    other,
                    child_first[1],
                    child_count[1],
                    depth + 1,
                    fork_depth
                );
            });
            subtree(
                b,
                starts[0],
                counts[0],
                boxes[0],
                nodes,
                child_first[0],
                child_count[0],
                depth + 1,
                fork_depth
            );
            right.get();
            uint32_t base = (uint32_t)nodes.size();
            for (Node& node : other) {
                for (int c = 0; c < 2; c++) {
                    if (node.count[c] == 0) {
                        node.first[c] += base;
                    }
                }
            }
            if (child_count[1] == 0) {
                child_first[1] += base;
            }
            nodes.insert(nodes.end(), other.begin(), other.end());
        } else {
            for (int c = 0; c < 2; c++) {
                subtree(
                    b,
                    starts[c],
                    counts[c],
                    boxes[c],
                    nodes,
                    child_first[c],
                    child_count[c],
                    depth + 1,
                    fork_depth
                );
            }
        }
        Node& node = nodes[at];
        for (int c = 0; c < 2; c++) {
            std::memcpy(node.low[c], boxes[c].low, sizeof(float) * 3);
            std::memcpy(node.high[c], boxes[c].high, sizeof(float) * 3);
            node.first[c] = child_first[c];
            node.count[c] = child_count[c];
        }
    }

    inline Tree* make(
        const float* tris,
        const int32_t* scene,
        long n,
        int leaf_most,
        bool median,
        int threads
    ) {
        Builder b{
            tris,
            std::vector<Box>(n),
            std::vector<float>(3 * n),
            std::vector<uint32_t>(n),
            leaf_most,
            median
        };
        for (long i = 0; i < n; i++) {
            const float* t = tris + 9 * i;
            float v1[3], v2[3];
            for (int a = 0; a < 3; a++) {
                v1[a] = t[a] + t[3 + a];
                v2[a] = t[a] + t[6 + a];
            }
            Box& box = b.boxes[i];
            box.reset();
            box.grow(t);
            box.grow(v1);
            box.grow(v2);
            for (int a = 0; a < 3; a++) {
                b.centre[3 * i + a] = 0.5f * (box.low[a] + box.high[a]);
            }
            b.order[i] = (uint32_t)i;
        }
        Tree* tree = new Tree;
        tree->root = bounds(b, 0, (uint32_t)n);
        int fork_depth = 0;
        while ((1 << fork_depth) < 2 * threads) {
            fork_depth++;
        }
        uint32_t first, count;
        subtree(
            b, 0, (uint32_t)n, tree->root, tree->nodes, first, count, 0, fork_depth
        );
        tree->root_count = count;
        if (count != 0) {
            // a root leaf: one node whose children are that leaf and an empty one
            Node node{};
            for (int a = 0; a < 3; a++) {
                node.low[0][a] = tree->root.low[a];
                node.high[0][a] = tree->root.high[a];
                node.low[1][a] = INFINITY;
                node.high[1][a] = -INFINITY;
            }
            node.first[0] = first;
            node.count[0] = count;
            node.first[1] = 0;
            node.count[1] = 1;
            tree->nodes.assign(1, node);
            tree->root_count = 0;
        }
        tree->tris.resize(9 * (size_t)n);
        tree->leaf.resize(n);
        tree->scene.resize(n);
        for (long i = 0; i < n; i++) {
            uint32_t t = b.order[i];
            std::memcpy(
                &tree->tris[9 * (size_t)i], tris + 9 * (size_t)t, sizeof(float) * 9
            );
            tree->leaf[i] = (int32_t)t;
            tree->scene[i] = scene[t];
        }
        return tree;
    }

    constexpr int CELL_BITS = 6;  // cells a side of the root box: 2^CELL_BITS

    // The rays' indices ordered by the cell of their origin in the root box (Morton
    // order of the cells, stable inside a cell).
    inline std::vector<uint32_t> by_cell(
        const Tree& tree, const float* origin, long n
    ) {
        const int side = 1 << CELL_BITS;
        std::vector<uint32_t> cell(n), order(n);
        std::vector<uint32_t> start((size_t)1 << (3 * CELL_BITS), 0);
        float scale[3];
        for (int a = 0; a < 3; a++) {
            float e = tree.root.high[a] - tree.root.low[a];
            scale[a] = e > 0.0f ? side / e : 0.0f;
        }
        for (long i = 0; i < n; i++) {
            uint32_t code = 0;
            for (int a = 0; a < 3; a++) {
                float x = (origin[3 * i + a] - tree.root.low[a]) * scale[a];
                uint32_t q = x <= 0.0f ? 0u : std::min((uint32_t)x, (uint32_t)side - 1);
                for (int bit = 0; bit < CELL_BITS; bit++) {
                    code |= ((q >> bit) & 1u) << (3 * bit + a);
                }
            }
            cell[i] = code;
            start[code]++;
        }
        uint32_t sum = 0;
        for (auto& one : start) {
            uint32_t count = one;
            one = sum;
            sum += count;
        }
        for (long i = 0; i < n; i++) {
            order[start[cell[i]]++] = (uint32_t)i;
        }
        return order;
    }

    // Both children's boxes against the ray: hit flags and entry distances.
    inline void child_boxes(
        const Node& node, const kr::Ray& ray, float best, bool hit[2], float entry[2]
    ) {
        for (int c = 0; c < 2; c++) {
            float near_[3], far_[3];
            for (int a = 0; a < 3; a++) {
                float to_low = (node.low[c][a] - ray.origin[a]) * ray.inverse[a];
                float to_high = (node.high[c][a] - ray.origin[a]) * ray.inverse[a];
                near_[a] = to_low < to_high ? to_low : to_high;
                far_[a] = to_low < to_high ? to_high : to_low;
            }
            float near_xy = near_[0] > near_[1] ? near_[0] : near_[1];
            float near_z = near_[2] > 0.0f ? near_[2] : 0.0f;
            entry[c] = near_xy > near_z ? near_xy : near_z;
            float far_xy = far_[0] < far_[1] ? far_[0] : far_[1];
            float exit_ = (far_xy < far_[2] ? far_xy : far_[2]) * kr::SLAB_SCALE;
            hit[c] = entry[c] <= (exit_ < best ? exit_ : best);
        }
    }

    // As kr::trace over the same triangles: the closest hit with t < tmax, ties to the
    // smaller scene triangle (any_hit: the first hit); hit.leaf the reference leaf.
    inline void trace(
        const Tree& tree, const kr::Ray& ray, float tmax, bool any_hit, kr::Hit& hit
    ) {
        hit.t = tmax;
        hit.u = hit.v = 0.0f;
        hit.leaf = -1;
        hit.nodes = hit.leaves = 0;
        float best = tmax;
        int32_t own = -1;
        uint32_t stack_first[STACK], stack_count[STACK];
        float stack_t[STACK];
        int size = 0;
        uint32_t first = 0, count = 0;  // the node or leaf being visited
        for (;;) {
            if (count != 0) {
                for (uint32_t i = first; i < first + count; i++) {
                    float t, u, v;
                    hit.leaves++;
                    if (!kr::triangle_test(&tree.tris[9 * (size_t)i], ray, t, u, v)) {
                        continue;
                    }
                    bool better = t < best;
                    if (!any_hit && !better && t == best && own >= 0) {
                        better = tree.scene[i] < tree.scene[own];
                    }
                    if (better) {
                        hit.t = t;
                        hit.u = u;
                        hit.v = v;
                        own = (int32_t)i;
                        hit.leaf = tree.leaf[i];
                        if (any_hit) {
                            return;
                        }
                        best = t;
                    }
                }
            } else {
                const Node& node = tree.nodes[first];
                bool hits[2];
                float entry[2];
                child_boxes(node, ray, best, hits, entry);
                hit.nodes += 2;
                for (int c = 0; c < 2; c++) {
                    if (hits[c]) {
                        __builtin_prefetch(
                            node.count[c]
                                ? (const void*)&tree.tris[9 * (size_t)node.first[c]]
                                : (const void*)&tree.nodes[node.first[c]]
                        );
                    }
                }
                if (hits[0] && hits[1]) {
                    int near_ = entry[1] < entry[0] ? 1 : 0;
                    stack_first[size] = node.first[1 - near_];
                    stack_count[size] = node.count[1 - near_];
                    stack_t[size++] = entry[1 - near_];
                    first = node.first[near_];
                    count = node.count[near_];
                    continue;
                }
                if (hits[0] || hits[1]) {
                    int c = hits[0] ? 0 : 1;
                    first = node.first[c];
                    count = node.count[c];
                    continue;
                }
            }
            for (;;) {
                if (size == 0) {
                    return;
                }
                size--;
                if (stack_t[size] <= best) {
                    break;
                }
            }
            first = stack_first[size];
            count = stack_count[size];
        }
    }

}  // namespace host
