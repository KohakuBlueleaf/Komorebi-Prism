// Lit SHADE on the pack thread: a row's three texels and its slot's words gathered into
// Dst, its surface (a, normal, specular) made there, and its rows out to the three
// parts.
#pragma once

#include <stdint.h>

#include "../../../../../../core/include/texel_pages/gather.hpp"
#include "../../../../../direct/light/kernels/pack/floats.hpp"
#include "winners.hpp"

namespace shade_k {

    using light_k::rsqrt_vector;

    // Dst after the records: kLitRows rows at a time, kGatherVectors vectors a row: the
    // texels (albedo linear, normal signed, specular unit), the slot's words 1 to 15.
    constexpr uint32_t kVecGather = 160;
    constexpr uint32_t kGatherVectors = 24;
    constexpr uint32_t kLitRows = 4;
    constexpr uint32_t kGAlbedo = 0, kGNormal = 3, kGSpecular = 6, kGSlot = 9;
    constexpr uint32_t kGBase = kGSlot, kGSpecularColour = kGSlot + 3;
    constexpr uint32_t kGTangent = kGSlot + 6, kGBitangent = kGSlot + 9;
    constexpr uint32_t kGTriangleNormal = kGSlot + 12;
    static_assert(kVecGather + kLitRows * kGatherVectors <= 256);
    static_assert(kGTriangleNormal + 3 == kGatherVectors);

    // Dst vector `vector` to row r of the plane page at `page`.
    inline void row_out(uint32_t vector, uint32_t page, uint32_t r, size_t vl) {
        __riscv_vsse32_v_u32m8(
            reinterpret_cast<uint32_t*>(page + 4 * (64 * (r >> 1) + (r & 1))),
            8,
            texel_pages::from_window(vector, vl),
            vl
        );
    }

    // Row r's gathered vectors from `at`: three texels by table, the slot's 15 words;
    // merging, the depth row 1 where the masked layer's pixel is taken (shade's rule).
    inline void gather_row(
        uint32_t r,
        uint32_t at,
        const uint32_t* index,
        const uint32_t* slot_offsets,
        const uint32_t* slot_words,
        const uint32_t* table,
        const uint32_t* texels,
        bool merging,
        size_t vl
    ) {
        const vuint32m8_t address = __riscv_vle32_v_u32m8(index + 32 * r, vl);
        const vuint32m8_t albedo_address = merging ? texel_pages::untagged(address, vl)
                                                   : address;
        if (merging) {
            const vuint32m8_t alpha_texel = texel_pages::texels(
                texels, texel_pages::mask_address(address, vl), vl
            );
            const vuint32m8_t triangle = texel_pages::from_window(kVecTri + r, vl);
            const vbool4_t take = __riscv_vmand_mm_b4(
                __riscv_vmsgeu_vx_u32m8_b4(alpha_texel, kAlphaOpaque << 24, vl),
                __riscv_vmsne_vx_u32m8_b4(triangle, kMinusOne, vl),
                vl
            );
            texel_pages::to_window(
                kVecDepth + r,
                __riscv_vmerge_vxm_u32m8(__riscv_vmv_v_x_u32m8(0, vl), 1, take, vl),
                vl
            );
        }
        const uint32_t* tables[3] = {
            table + kTabGamma, table + kTabSigned, table + kTabUnit
        };
        for (uint32_t texture = 0; texture < 3; ++texture) {
            const vuint32m8_t texel = texel_pages::texels(
                texels,
                texture == 0
                    ? albedo_address
                    : __riscv_vle32_v_u32m8(index + 1024 * texture + 32 * r, vl),
                vl
            );
            for (uint32_t channel = 0; channel < 3; ++channel) {
                texel_pages::decode_to(
                    tables[texture], texel, channel, at + 3 * texture + channel, vl
                );
            }
        }
        const vuint32m8_t offset = __riscv_vle32_v_u32m8(slot_offsets + 32 * r, vl);
        for (uint32_t w = 1; w < kLitSlotWords; ++w) {
            texel_pages::to_window(
                at + kGSlot + w - 1,
                __riscv_vluxei32_v_u32m8(slot_words + w, offset, vl),
                vl
            );
        }
    }

    // A row's surface from its gathered vectors at `at`: a = linear albedo x base,
    // specular x its colour, the normal (T tx + B ty) + N tz over its length.
    inline void surface_row(uint32_t at) {
        TTI_SFPENCC(3, 0, 0, 10);
        for (uint32_t channel = 0; channel < 3; ++channel) {
            load(L0, at + kGAlbedo + channel);
            load(L1, at + kGBase + channel);
            mul(L0, L1, L2);
            store(L2, at + kGAlbedo + channel);
            load(L0, at + kGSpecular + channel);
            load(L1, at + kGSpecularColour + channel);
            mul(L0, L1, L2);
            store(L2, at + kGSpecular + channel);
        }
        load(L0, at + kGNormal);
        load(L1, at + kGNormal + 1);
        load(L2, at + kGNormal + 2);
        for (uint32_t axis = 0; axis < 3; ++axis) {
            load(L3, at + kGTangent + axis);
            load(L4, at + kGBitangent + axis);
            load(L5, at + kGTriangleNormal + axis);
            mul(L3, L0, L6);
            TT_SFPMAD(L4, L1, L6, L6, 0);
            TT_SFPMAD(L5, L2, L6, L6, 0);
            store(L6, at + kGNormal + axis);
        }
        load(L0, at + kGNormal);
        load(L1, at + kGNormal + 1);
        load(L2, at + kGNormal + 2);
        mul(L0, L0, L3);
        TT_SFPMAD(L1, L1, L3, L3, 0);
        TT_SFPMAD(L2, L2, L3, L3, 0);
        rsqrt_vector(L3, L4, L5, L6, L7);
        for (uint32_t axis = 0; axis < 3; ++axis) {
            mul(axis == 0 ? L0 : axis == 1 ? L1 : L2, L4, L6);
            store(L6, at + kGNormal + axis);
        }
    }

    // The three parts' pages of an item in the out ring (each five pages, none wraps).
    struct Parts {
        uint32_t address[kLitParts];

        void place(uint32_t first) {
            const uint32_t limit = get_local_cb_interface(kFieldOutRing).fifo_limit
                << 4;
            const uint32_t size = get_local_cb_interface(kFieldOutRing).fifo_size << 4;
            uint32_t at = first;
            for (uint32_t part = 0; part < kLitParts; ++part) {
                address[part] = at;
                at += kShadeOutPages * kOutPageBytes;
                if (at >= limit) {
                    at -= size;
                }
            }
        }

        uint32_t page(uint32_t part, uint32_t plane) const {
            return address[part] + plane * kOutPageBytes;
        }
    };

    // Row r's surface to the parts: the material word | a, normal x, y | normal z,
    // visibility, specular.
    inline void surface_out(
        uint32_t r,
        uint32_t at,
        const Parts& parts,
        const uint32_t* slot_offsets,
        const uint32_t* slot_words,
        size_t vl
    ) {
        __riscv_vsse32_v_u32m8(
            reinterpret_cast<uint32_t*>(
                parts.page(0, kPlanes - 1) + 4 * (64 * (r >> 1) + (r & 1))
            ),
            8,
            __riscv_vluxei32_v_u32m8(
                slot_words, __riscv_vle32_v_u32m8(slot_offsets + 32 * r, vl), vl
            ),
            vl
        );
        // surface plane p: part 1 + p / 5, its page p % 5
        constexpr uint32_t kSources = kSurfacePlanes - 1;  // the gathered ones
        const uint32_t vectors[kSources] = {
            at + kGAlbedo,
            at + kGAlbedo + 1,
            at + kGAlbedo + 2,
            at + kGNormal,
            at + kGNormal + 1,
            at + kGNormal + 2,
            at + kGSpecular,
            at + kGSpecular + 1,
            at + kGSpecular + 2
        };
        for (uint32_t plane = 0; plane < kSurfacePlanes; ++plane) {
            const uint32_t vector = plane == kSurfaceVisibility ? kVecBlue + r
                : plane < kSurfaceVisibility                    ? vectors[plane]
                                                                : vectors[plane - 1];
            row_out(vector, parts.page(1 + plane / kPlanes, plane % kPlanes), r, vl);
        }
    }

}  // namespace shade_k
