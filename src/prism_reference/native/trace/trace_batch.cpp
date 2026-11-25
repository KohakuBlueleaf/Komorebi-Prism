// Many rays at once over the reference tree (raytrace_core.hpp's walk and triangle
// test), threaded: the batch ray routine of prism_reference.trace.batch, a library.
#include <atomic>
#include <cstdint>
#include <thread>
#include <vector>

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
