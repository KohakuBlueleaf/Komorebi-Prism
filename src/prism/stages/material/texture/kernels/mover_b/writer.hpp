// SHADE on mover B: each item's colour planes to the frame (a band its rows; merging
// the opaque layer's frame, kShadeMergedDepth its 1/z too; lit three parts: the frame's
// planes 0 and 4, the surface's two frames), then the profile.
#pragma once

#include <stdint.h>

#include "../mover_a/directory.hpp"

namespace shade_k {

    using fill_k::kItemEmpty;
    using fill_k::kItemRow0Shift;
    using fill_k::kItemRow1Shift;
    using fill_k::kItemRowMask;
    using fill_k::kItemSlot;
    using fill_k::kOutPageBytes;
    using fill_k::kPlanes;
    using fill_k::kRowBytes;

    static_assert(kShadeOutPages == kPlanes);

    // A bad item or frame: recorded in the writer's word, the run stopped.
    template <typename Mover>
    bool bad_item(const Mover& mover, const km_command_t& command, uint32_t where) {
        mover.gave_up(km::kStWriter, fill_k::kGaveBadItem, where, 0, command.sequence);
        *mover.control(KM_CONTROL_STOP) = 1;
        return false;
    }

    // Writes sent within the run's wait limit (false: gave up, recorded).
    template <typename Mover>
    bool writes_sent(const Mover& mover, const km_command_t& command) {
        const uint32_t code = mover.poll(
            [] {
                return ncrisc_noc_nonposted_writes_sent(noc_index);
            },
            mover.args().wait_limit
        );
        if (code == km::kGaveNone) {
            return true;
        }
        mover.gave_up(km::kStWriter, code, fill_k::kWhereFlush, 0, command.sequence);
        return false;
    }

    // The out item at the front within the buffer (it never wraps), else bad.
    template <typename Mover>
    bool out_front(const Mover& mover, const km_command_t& command) {
        if (!mover.wait_front(kFieldOutRing, kShadeOutPages)) {
            return false;
        }
        if (get_read_ptr(kFieldOutRing) + kShadeOutPages * kOutPageBytes >
            get_local_cb_interface(kFieldOutRing).fifo_limit) {
            return bad_item(mover, command, fill_k::kWhereBadSend);
        }
        return true;
    }

    // Planes [first, end) of an out item's rows at `source` to the frame of `words`
    // (its pages a tensor, then their addresses) at its page `page`; unlit the colour
    // planes from the item's first page; `frame_part` (lit part 0) planes 0 and 4 only.
    inline void write_part(
        uint32_t source,
        const uint32_t* words,
        uint32_t page,
        uint32_t byte_offset,
        uint32_t bytes,
        uint32_t first,
        uint32_t end,
        bool lit,
        bool frame_part
    ) {
        const InterleavedAddrGen<true> tensor = {
            .bank_base_address = words[1 + page / words[0]], .page_size = kOutPageBytes
        };
        for (uint32_t plane = first; plane < end; ++plane) {
            if (frame_part && plane != 0 && plane != kPlanes - 1) {
                continue;
            }
            const uint32_t from = lit ? plane : plane - kShadeFirstPlane;
            noc_async_write(
                source + from * kOutPageBytes,
                get_noc_addr((page + plane) % words[0], tensor, byte_offset),
                bytes
            );
        }
    }

    // SHADE on mover B: the directory's items' colour planes written to the frame
    // (merging, the opaque layer's), the profile to page `rank` of `profile`.
    template <
        typename Directories,
        typename Lists,
        typename Textures,
        typename TableTensor,
        typename Profiles,
        typename Surface>
    inline bool shade_writer(
        km::Movement& movement,
        const km_command_t& command,
        const Directories& directory,
        const Lists& lists,
        const Textures& textures,
        const TableTensor& table,
        const Profiles& profile,
        uint32_t opaque,
        uint32_t mode,
        uint32_t grid,
        uint32_t camera,
        const Surface& surface
    ) {
        static_cast<void>(lists);
        static_cast<void>(textures);
        static_cast<void>(table);
        static_cast<void>(grid);
        const uint32_t rank = movement.me() - km::first(command);
        // unlit, the masked layer's command before a glass layer's: the merged 1/z too
        const bool lit = camera != 0;
        const bool merged_depth =
            (opaque != 0 && !lit &&
             (mode & (kShadeMergedDepth | kShadeGlass)) == kShadeMergedDepth);
        Directory words;
        bool valid = true;
        // lit: the surface's two frames' words
        if (lit &&
            !words.read_surface(
                movement, surface.word, rank, get_write_ptr(kDirB), valid
            )) {
            return false;
        }
        const bool surface_valid = valid;
        if (!words.read(
                movement, directory.word, opaque, rank, get_write_ptr(kDirB), valid
            )) {
            return false;
        }
        // the frame written: the directory's own, or the opaque layer's
        uint32_t frame[kDirFrameMax + 1] = {};
        for (uint32_t i = 0; i <= kDirFrameMax; ++i) {
            frame[i] = opaque != 0 ? words.opaque[i] : words.words[kDirFrame + i];
        }
        const uint32_t tensor_pages = frame[0];
        if (tensor_pages == 0 || tensor_pages % kPlanes != 0 ||
            words.items > kDirMaxItems || !surface_valid) {
            return bad_item(movement, command, kWhereShadeBad);
        }
        const uint32_t* second = words.surface + kDirFrameMax + 1;
        for (uint32_t item = 0; item < words.items; ++item) {
            const uint32_t id = words.words[kDirIds + item];
            if ((id & kItemEmpty) != 0) {
                continue;  // no triangle: FILL's background stays
            }
            const uint32_t page = (id & kItemSlot) * kPlanes;
            if (page / tensor_pages >= kDirFrameMax ||
                (lit &&
                 (page / words.surface[0] >= kDirFrameMax ||
                  page / second[0] >= kDirFrameMax))) {
                return bad_item(movement, command, kWhereShadeBad);
            }
            const uint32_t first_row = id >> kItemRow0Shift & kItemRowMask;
            const uint32_t end_row = id >> kItemRow1Shift & kItemRowMask;
            const uint32_t byte_offset = first_row * kRowBytes;
            const uint32_t bytes =
                (end_row > 0 ? (end_row - first_row) * kRowBytes : kOutPageBytes);
            // not lit: the colour planes; lit: the frame's 1/z (merging) and material
            // word, the surface's planes 0 to 4, 5 to 9
            for (uint32_t part = 0; part < (lit ? kLitParts : 1); ++part) {
                if (!out_front(movement, command)) {
                    return false;
                }
                const uint32_t source = get_read_ptr(kFieldOutRing) + byte_offset;
                // part 0 the frame's, then the surface's first and second frame
                const uint32_t* written = part == 0
                    ? frame
                    : words.surface + (kDirFrameMax + 1) * (part - 1);
                const uint32_t first_plane = !lit ? kShadeFirstPlane
                    : part == 0 && opaque == 0    ? kPlanes - 1
                                                  : 0;
                write_part(
                    source,
                    written,
                    page,
                    byte_offset,
                    bytes,
                    first_plane,
                    lit ? kPlanes : kShadeFirstPlane + kShadeColourPages,
                    lit,
                    lit && part == 0
                );
                if (merged_depth) {  // the fourth page: the merged 1/z, the frame's 0
                    const InterleavedAddrGen<true> tensor = {
                        .bank_base_address = frame[1 + page / tensor_pages],
                        .page_size = kOutPageBytes
                    };
                    noc_async_write(
                        source + kShadeColourPages * kOutPageBytes,
                        get_noc_addr(page % tensor_pages, tensor, byte_offset),
                        bytes
                    );
                }
#if defined(PRISM_SHADE_TRANSMIT)
                if (lit && part == 0 && (mode & kShadeTransmit) != 0) {  // T's codes
                    const InterleavedAddrGen<true> tensor = {
                        .bank_base_address = frame[1 + page / tensor_pages],
                        .page_size = kOutPageBytes
                    };
                    noc_async_write(
                        source + kOutPageBytes,
                        get_noc_addr((page + 1) % tensor_pages, tensor, byte_offset),
                        bytes
                    );
                }
#endif
                if (!writes_sent(movement, command)) {
                    return false;
                }
                cb_pop_front(kFieldOutRing, kShadeOutPages);
            }
        }
        // the profile item: the pack thread's counters in its first words
        if (!out_front(movement, command)) {
            return false;
        }
        if (profile.word != 0) {
            const InterleavedAddrGen<true> profiles = {
                .bank_base_address = profile.word, .page_size = kShadeProfBytes
            };
            noc_async_write(
                get_read_ptr(kFieldOutRing),
                get_noc_addr(rank, profiles),
                kShadeProfBytes
            );
            if (!writes_sent(movement, command)) {
                return false;
            }
        }
        cb_pop_front(kFieldOutRing, kShadeOutPages);
        return true;
    }

}  // namespace shade_k
