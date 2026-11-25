// Shared by the C++ helpers: the hash of prism_reference.scene.generated and small
// helpers.
#pragma once

#include <cstdint>

#ifdef __CUDACC__
#define KR_HD __host__ __device__
#else
#define KR_HD
#endif

namespace kr {

    constexpr int WIDTH = 1024;
    constexpr int HEIGHT = 1024;
    constexpr int TILE = 32;
    constexpr int TILES_X = WIDTH / TILE;
    constexpr int TILES_Y = HEIGHT / TILE;

    KR_HD inline uint32_t hash32(uint32_t index, uint32_t stream, uint32_t seed) {
        uint32_t h = index * 0x9E3779B1u + (stream + 1u) * 0x85EBCA6Bu + seed;
        h ^= h >> 16;
        h *= 0x7FEB352Du;
        h ^= h >> 15;
        h *= 0x846CA68Bu;
        return h ^ (h >> 16);
    }

    KR_HD inline float uniform(uint32_t index, uint32_t stream, uint32_t seed) {
        return (float)(hash32(index, stream, seed) >> 8) * (1.0f / 16777216.0f);
    }

}  // namespace kr
