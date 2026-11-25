// The pack thread's side of the texel pages (SHADE, LIGHT): Dst rows as vectors, a
// pass's pages and their slots, a row's keys turned into texel addresses in the slots.
#pragma once

#include <stdint.h>

#include "../sfpu.hpp"
#include "protocol.h"

#if defined(__riscv_vector)
#include <riscv_vector.h>
#endif

namespace texel_pages {

    using pack_sfpu::window;
    using pack_sfpu::word;

    // Dst vector `vector` (its 32 words, a row) as a register.
    inline vuint32m8_t from_window(uint32_t vector, size_t vl) {
        return (__riscv_vlse32_v_u32m8(
            const_cast<const uint32_t*>(window() + word(vector)), 8, vl
        ));
    }

    // `value` to Dst vector `vector`.
    inline void to_window(uint32_t vector, vuint32m8_t value, size_t vl) {
        __riscv_vsse32_v_u32m8(
            const_cast<uint32_t*>(window() + word(vector)), 8, value, vl
        );
    }

    // The pages of a pass of rows: an open-addressed table of (1 + page) -> slot, the
    // slots' pages in order, and the last page found.
    struct Pages {
        uint32_t* keys;   // kPagesHashSize words: 1 + page, 0 empty
        uint32_t* slots;  // kPagesHashSize words
        uint32_t* used;   // kShadeSlots words: the table places filled
        uint32_t* ask;    // the ask page being written: count, then the pages
        uint32_t count = 0, last_page = 0xFFFFFFFF, last_slot = 0;

        // The table at `words` (2 kPagesHashSize + kShadeSlots words), emptied.
        void place(uint32_t* words) {
            keys = words;
            slots = keys + kPagesHashSize;
            used = slots + kPagesHashSize;
            for (uint32_t i = 0; i < kPagesHashSize; ++i) {
                keys[i] = 0;
            }
        }

        void clear() {
            for (uint32_t i = 0; i < count; ++i) {
                keys[used[i]] = 0;
            }
            count = 0;
            last_page = 0xFFFFFFFF;
        }

        // The slot of `page`; kShadeSlots when the slots are full.
        uint32_t slot_of(uint32_t page) {
            if (page == last_page) {
                return last_slot;
            }
            uint32_t place = (page * 2654435761u) >> 24;
            for (;;) {
                const uint32_t key = keys[place];
                if (key == page + 1) {
                    break;
                }
                if (key == 0) {
                    if (count == kShadeSlots) {
                        return kShadeSlots;
                    }
                    keys[place] = page + 1;
                    slots[place] = count;
                    used[count] = place;
                    ask[1 + count] = page;
                    ++count;
                    break;
                }
                place = (place + 1) & (kPagesHashSize - 1);
            }
            last_page = page;
            last_slot = slots[place];
            return last_slot;
        }
    };

    // `out` plus delta(slot, page) on the lanes `pending` of `page`, per distinct page
    // (`last`: the last page first, then reductions); `fits` false when slots are full
    template <typename Delta>
    inline vuint32m8_t add_slots(
        Pages& pages,
        vuint32m8_t page,
        vbool4_t pending,
        vuint32m8_t out,
        Delta delta,
        bool last,
        bool& fits,
        size_t vl
    ) {
        constexpr uint32_t kNone = 0xFFFFFFFF;  // past any page: none pending
        if (last && pages.last_page != kNone) {
            const vbool4_t same = (__riscv_vmseq_vx_u32m8_b4_mu(
                pending, __riscv_vmclr_m_b4(vl), page, pages.last_page, vl
            ));
            out = (__riscv_vadd_vx_u32m8_mu(
                same, out, out, delta(pages.last_slot, pages.last_page), vl
            ));
            pending = __riscv_vmandn_mm_b4(pending, same, vl);
        }
        const vuint32m1_t none = __riscv_vmv_v_x_u32m1(kNone, 1);
        for (;;) {
            uint32_t least = kNone;
            if (last) {
                least = (__riscv_vmv_x_s_u32m1_u32(
                    __riscv_vredminu_vs_u32m8_u32m1_m(pending, page, none, vl)
                ));
            } else {  // many pages a row (SHADE): the first pending lane's
                const long lane = __riscv_vfirst_m_b4(pending, vl);
                if (lane >= 0) {
                    least = (__riscv_vmv_x_s_u32m8_u32(
                        __riscv_vslidedown_vx_u32m8(page, static_cast<size_t>(lane), vl)
                    ));
                }
            }
            if (least == kNone) {
                return out;
            }
            const uint32_t slot = pages.slot_of(least);
            if (slot == kShadeSlots) {
                fits = false;
                return out;
            }
            const vbool4_t same = (__riscv_vmseq_vx_u32m8_b4_mu(
                pending, __riscv_vmclr_m_b4(vl), page, least, vl
            ));
            out = __riscv_vadd_vx_u32m8_mu(same, out, out, delta(slot, least), vl);
            pending = __riscv_vmandn_mm_b4(pending, same, vl);
        }
    }

    // No tag vector (row_addresses).
    constexpr uint32_t kNoTags = 0xFFFFFFFF;

    // A row's keys as texel addresses into `to` (`none`: no page; `tags`: the mask's
    // slot too); -1 when the pages do not fit, else the texels with `count`, or 0
    inline int32_t row_addresses(
        Pages& pages,
        vuint32m8_t key,
        uint32_t tags,
        uint32_t* to,
        uint32_t page_limit,
        uint32_t none,
        bool count,
        bool last,
        size_t vl
    ) {
        // a key under 1,024 makes page 2^32 - 1, past any limit
        const vuint32m8_t page = (__riscv_vsub_vx_u32m8(
            __riscv_vsrl_vx_u32m8(key, 10, vl), 1, vl
        ));
        const vbool4_t valid = __riscv_vmsltu_vx_u32m8_b4(page, page_limit, vl);
        // 4 x key = (1 + page) x page bytes + 4 x texel: the page's slot adds
        // (slot - 1 - page) x page bytes
        bool fits = true;
        vuint32m8_t out = add_slots(
            pages,
            page,
            valid,
            __riscv_vsll_vx_u32m8(key, 2, vl),
            [](uint32_t slot, uint32_t first) {
                return (slot - 1 - first) * kTexPageBytes;
            },
            last,
            fits,
            vl
        );
        if (fits && tags != kNoTags) {
            const vuint32m8_t tag = from_window(tags, vl);
            const vuint32m8_t mask_page = (__riscv_vsub_vx_u32m8(
                __riscv_vsrl_vx_u32m8(
                    __riscv_vand_vx_u32m8(tag, 0x3FFFFFFF, vl), 10, vl
                ),
                1,
                vl
            ));
            const vbool4_t masked = (__riscv_vmand_mm_b4(
                __riscv_vmand_mm_b4(
                    __riscv_vmsgeu_vx_u32m8_b4(tag, 3u << 30, vl),
                    __riscv_vmsltu_vx_u32m8_b4(mask_page, page_limit, vl),
                    vl
                ),
                valid,
                vl
            ));
            out = add_slots(
                pages,
                mask_page,
                masked,
                out,
                [](uint32_t slot, uint32_t) {
                    return (slot + 1) << kMaskSlotShift;
                },
                false,
                fits,
                vl
            );
        }
        if (!fits) {
            return -1;
        }
        __riscv_vse32_v_u32m8(
            to,
            __riscv_vmerge_vxm_u32m8(out, none, __riscv_vmnot_m_b4(valid, vl), vl),
            vl
        );
        return count ? static_cast<int32_t>(__riscv_vcpop_m_b4(valid, vl)) : 0;
    }

}  // namespace texel_pages
