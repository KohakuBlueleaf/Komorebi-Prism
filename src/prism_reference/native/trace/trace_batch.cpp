// Many rays at once over the reference tree (raytrace_core.hpp's walk and triangle
// test) or over the host's own tree of its triangles (host_tree.hpp), threaded: the
// batch ray routines of prism_reference.trace.batch, a library.
#include <atomic>
#include <cstdint>
#include <thread>
#include <vector>

#include "host_tree.hpp"
#include "raytrace_core.hpp"

// Rays i < n from origin + t direction, t < tmax[i]; any_hit stops at the first hit.
// Writes t, leaf (-1: none), u, v of each ray.
extern "C" void trace_batch(
    const uint32_t* nodes,
    const float* tris,
    const int32_t* leaf_tri,
    const float* origin,
    const float* direction,
    const float* tmax,
    long n,
    int any_hit,
    float* t,
    int32_t* leaf,
    float* u,
    float* v,
    int threads
) {
    kr::Tree tree{nodes, tris, leaf_tri};
    std::atomic<long> next{0};
    const long block = 1024;
    auto work = [&]() {
        for (;;) {
            long start = next.fetch_add(block);
            if (start >= n) {
                return;
            }
            long end = start + block < n ? start + block : n;
            for (long i = start; i < end; i++) {
                kr::Ray ray;
                kr::make_ray(ray, origin + 3 * i, direction + 3 * i);
                kr::Hit hit;
                kr::trace(tree, ray, tmax[i], any_hit != 0, hit);
                t[i] = hit.t;
                leaf[i] = hit.leaf;
                u[i] = hit.u;
                v[i] = hit.v;
            }
        }
    };
    std::vector<std::thread> pool;
    for (int k = 0; k < threads; k++) {
        pool.emplace_back(work);
    }
    for (auto& worker : pool) {
        worker.join();
    }
}

// The host's tree over the reference tree's triangles (n, 9) in leaf order, `scene`
// each one's scene triangle; leaves of at most leaf_most triangles, median cuts when
// `median`; built on `threads` threads. Freed by host_tree_free.
extern "C" void* host_tree_make(
    const float* tris,
    const int32_t* scene,
    long n,
    int leaf_most,
    int median,
    int threads
) {
    return host::make(tris, scene, n, leaf_most, median != 0, threads);
}

extern "C" void host_tree_free(void* tree) {
    delete static_cast<host::Tree*>(tree);
}

// As trace_batch over the host's tree: leaf is the reference tree's leaf.
extern "C" void host_trace_batch(
    const void* tree,
    const float* origin,
    const float* direction,
    const float* tmax,
    long n,
    int any_hit,
    float* t,
    int32_t* leaf,
    float* u,
    float* v,
    int threads
) {
    const host::Tree& own = *static_cast<const host::Tree*>(tree);
    std::vector<uint32_t> order = host::by_cell(own, origin, n);
    std::atomic<long> next{0};
    const long block = 1024;
    auto work = [&]() {
        for (;;) {
            long start = next.fetch_add(block);
            if (start >= n) {
                return;
            }
            long end = start + block < n ? start + block : n;
            for (long k = start; k < end; k++) {
                long i = order[k];
                kr::Ray ray;
                kr::make_ray(ray, origin + 3 * i, direction + 3 * i);
                kr::Hit hit;
                host::trace(own, ray, tmax[i], any_hit != 0, hit);
                t[i] = hit.t;
                leaf[i] = hit.leaf;
                u[i] = hit.u;
                v[i] = hit.v;
            }
        }
    };
    if (threads <= 1) {
        work();
        return;
    }
    std::vector<std::thread> pool;
    for (int k = 0; k < threads; k++) {
        pool.emplace_back(work);
    }
    for (auto& worker : pool) {
        worker.join();
    }
}
