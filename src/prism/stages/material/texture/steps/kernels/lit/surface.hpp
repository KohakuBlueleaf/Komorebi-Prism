// The lit material on the pack CPU (pack/lit/surface.hpp's, its parts any three places
// of five pages in L1): a row's three texels and its slot's words gathered into Dst,
// its surface (a, normal, specular) made there, its rows out to the three parts.
#pragma once

#include <stdint.h>

#include "../../../../../../core/include/texel_pages/gather.hpp"
#include "../../../../../direct/light/kernels/pack/floats.hpp"
#include "../../../kernels/pack/lit/winners.hpp"

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
    // after the normal: its texel's length r (then r s), D and s of the widening
    constexpr uint32_t kGLength = kGTangent, kGSpread = kGTangent + 1;
    constexpr uint32_t kGExponent = kGTangent + 2;
    constexpr uint32_t kGReciprocal = kGBitangent;  // q of the widening
    // 1 / (1 - 1 / 128): a byte-rounded unit vector's length read as 1
    constexpr uint32_t kUnitRounding = 0x3F810204;
    constexpr uint32_t kReciprocalSeed = 0x7EF311C3;  // 1 / x's first guess, by bits
    constexpr float kLeastLength = 1e-4f;  // the least normal length r widened by
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

    // A row's surface from its gathered vectors at `at`: a = linear albedo x base x r,
    // specular x its colour, the normal (T tx + B ty) + N tz over its length; r =
    // min(|t| / (1 - 1 / 128), 1) of the normal texel t (the white texel without a
    // map: 1) to kGLength (surface_out widens the lobe by it).
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
        mul(L0, L0, L3);
        TT_SFPMAD(L1, L1, L3, L3, 0);
        TT_SFPMAD(L2, L2, L3, L3, 0);
        rsqrt_vector(L3, L4, L5, L6, L7);
        mul(L3, L4, L7);
        immediate(L5, kUnitRounding);
        mul(L7, L5, L7);
        add(ONE, ZERO, L5);
        TTI_SFPNOP;
        TT_SFPSWAP(0, L5, L7, kMinMax);
        for (uint32_t axis = 0; axis < 3; ++axis) {
            load(L3, at + kGTangent + axis);
            load(L4, at + kGBitangent + axis);
            load(L5, at + kGTriangleNormal + axis);
            mul(L3, L0, L6);
            TT_SFPMAD(L4, L1, L6, L6, 0);
            TT_SFPMAD(L5, L2, L6, L6, 0);
            store(L6, at + kGNormal + axis);
        }
        store(L7, at + kGLength);
        for (uint32_t channel = 0; channel < 3; ++channel) {
            load(L3, at + kGAlbedo + channel);
            mul(L3, L7, L3);
            store(L3, at + kGAlbedo + channel);
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

    // The three parts of a tile's surface, five pages each: the frame's planes (1/z,
    // the material word in the last), the surface's planes 0 to 4, 5 to 9.
    struct Parts {
        uint32_t address[kLitParts];

        uint32_t page(uint32_t part, uint32_t plane) const {
            return address[part] + plane * kOutPageBytes;
        }
    };

    // A window vector read as floats
    inline vfloat32m8_t window_floats(uint32_t vector, size_t vl) {
        return __riscv_vreinterpret_v_u32m8_f32m8(texel_pages::from_window(vector, vl));
    }

    // 1 / x for x > 0: the bit pattern's seed, then three Newton steps y (2 - x y)
    inline vfloat32m8_t reciprocal(vfloat32m8_t x, size_t vl) {
        vfloat32m8_t y = __riscv_vreinterpret_v_u32m8_f32m8(__riscv_vrsub_vx_u32m8(
            __riscv_vreinterpret_v_f32m8_u32m8(x), kReciprocalSeed, vl
        ));
        for (uint32_t step = 0; step < 3; ++step) {
            y = __riscv_vfmul_vv_f32m8(
                y,
                __riscv_vfrsub_vf_f32m8(__riscv_vfmul_vv_f32m8(x, y, vl), 2.0f, vl),
                vl
            );
        }
        return y;
    }

    // Row r's lobe widened by r (Toksvig: s' = max(rint(r s / (r + s (1 - r))), 1),
    // 0 kept; the specular x (1 + s') / (1 + s)), then its surface to the parts: the
    // material word (exponent s') | a, normal x, y | normal z, visibility, specular.
    inline void surface_out(
        uint32_t r,
        uint32_t at,
        const Parts& parts,
        const uint32_t* slot_offsets,
        const uint32_t* slot_words,
        size_t vl
    ) {
        const vfloat32m8_t s = __riscv_vfcvt_f_xu_v_f32m8(
            __riscv_vand_vx_u32m8(
                __riscv_vsrl_vx_u32m8(
                    __riscv_vluxei32_v_u32m8(
                        slot_words, __riscv_vle32_v_u32m8(slot_offsets + 32 * r, vl), vl
                    ),
                    kMaterialExponentShift,
                    vl
                ),
                kExponentMax,
                vl
            ),
            vl
        );
        texel_pages::to_window(
            at + kGExponent, __riscv_vreinterpret_v_f32m8_u32m8(s), vl
        );
        const vfloat32m8_t length = __riscv_vfmax_vf_f32m8(
            window_floats(at + kGLength, vl), kLeastLength, vl
        );
        texel_pages::to_window(
            at + kGSpread,
            __riscv_vreinterpret_v_f32m8_u32m8(__riscv_vfmacc_vv_f32m8(
                length, s, __riscv_vfrsub_vf_f32m8(length, 1.0f, vl), vl
            )),
            vl
        );
        texel_pages::to_window(
            at + kGLength,
            __riscv_vreinterpret_v_f32m8_u32m8(__riscv_vfmul_vv_f32m8(length, s, vl)),
            vl
        );
        // q = 1 / (D (1 + s)), D = r + s (1 - r): s' = r s (1 + s) q, the lobe (1 + s')
        // D q
        const vfloat32m8_t q = reciprocal(
            __riscv_vfmul_vv_f32m8(
                window_floats(at + kGSpread, vl),
                __riscv_vfadd_vf_f32m8(window_floats(at + kGExponent, vl), 1.0f, vl),
                vl
            ),
            vl
        );
        texel_pages::to_window(
            at + kGReciprocal, __riscv_vreinterpret_v_f32m8_u32m8(q), vl
        );
        asm volatile("" ::: "memory");  // read the window again: no vector kept
        const vint32m8_t rounded = __riscv_vfcvt_x_f_v_i32m8(
            __riscv_vfmul_vv_f32m8(
                window_floats(at + kGLength, vl),
                __riscv_vfmul_vv_f32m8(
                    __riscv_vfadd_vf_f32m8(
                        window_floats(at + kGExponent, vl), 1.0f, vl
                    ),
                    window_floats(at + kGReciprocal, vl),
                    vl
                ),
                vl
            ),
            vl
        );
        asm volatile("" ::: "memory");  // read the window again: no vector kept
        const vuint32m8_t wide = __riscv_vmerge_vxm_u32m8(
            __riscv_vreinterpret_v_i32m8_u32m8(__riscv_vmax_vx_i32m8(rounded, 1, vl)),
            0,
            __riscv_vmfeq_vf_f32m8_b4(window_floats(at + kGExponent, vl), 0.0f, vl),
            vl
        );
        asm volatile("" ::: "memory");  // read the window again: no vector kept
        const vfloat32m8_t lobe = __riscv_vfmul_vv_f32m8(
            __riscv_vfmul_vv_f32m8(
                window_floats(at + kGSpread, vl),
                window_floats(at + kGReciprocal, vl),
                vl
            ),
            __riscv_vfadd_vf_f32m8(__riscv_vfcvt_f_xu_v_f32m8(wide, vl), 1.0f, vl),
            vl
        );
        for (uint32_t channel = 0; channel < 3; ++channel) {
            const uint32_t vector = at + kGSpecular + channel;
            const vfloat32m8_t value = __riscv_vreinterpret_v_u32m8_f32m8(
                texel_pages::from_window(vector, vl)
            );
            texel_pages::to_window(
                vector,
                __riscv_vreinterpret_v_f32m8_u32m8(
                    __riscv_vfmul_vv_f32m8(value, lobe, vl)
                ),
                vl
            );
        }
        const vuint32m8_t word = __riscv_vluxei32_v_u32m8(
            slot_words, __riscv_vle32_v_u32m8(slot_offsets + 32 * r, vl), vl
        );
        const vuint32m8_t widened = __riscv_vor_vv_u32m8(
            __riscv_vand_vx_u32m8(word, ~(kExponentMax << kMaterialExponentShift), vl),
            __riscv_vsll_vx_u32m8(wide, kMaterialExponentShift, vl),
            vl
        );
        __riscv_vsse32_v_u32m8(
            reinterpret_cast<uint32_t*>(
                parts.page(0, kPlanes - 1) + 4 * (64 * (r >> 1) + (r & 1))
            ),
            8,
            widened,
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
