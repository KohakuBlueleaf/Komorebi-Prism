// FILL on the movers: each directory item's planes (or the empty tile's) written into
// the frame's pages on mover B, and the reader's and writer's profile words.
#pragma once

#include <stdint.h>

#include "../common/layouts.hpp"
#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"
#include "komorebi/device/tensors/km_ask.hpp"

namespace fill_k {

    // Mover B's state for one command: the frame's tensors from the directory, the
    // filled items' buffer and the empty tile's planes, its cycles.
    struct Items {
        uint32_t out = 0;    // the items' planes, from the pack thread
        uint32_t empty = 0;  // the empty tile's planes (L1)
        uint32_t started = km::wall();
        uint32_t wait = 0, write = 0, items = 0;
        uint32_t tensor_pages = 0;  // pages a frame tensor
        uint32_t bases[kDirFrameMax] = {};

        // The command's buffers: the items' planes and the empty tile's (L1).
        void start(uint32_t planes, uint32_t empty_planes) {
            out = planes;
            empty = empty_planes;
        }

        // A gave-up NoC wait or a bad item, recorded by the writer.
        template <typename Writer>
        bool bad(const Writer& writer, const km_command_t& command, uint32_t where) {
            writer.gave_up(km::kStWriter, kGaveBadItem, where, 0, command.sequence);
            *writer.control(KM_CONTROL_STOP) = 1;
            return false;
        }

        // The directory's items' count and frame words (pages a tensor, then each
        // one's address); false: they are not a frame (recorded).
        template <typename Writer, typename... Words>
        bool frame(
            const Writer& writer,
            const km_command_t& command,
            uint32_t item_count,
            Words... words
        ) {
            static_assert(sizeof...(Words) == 1 + kDirFrameMax);
            const uint32_t frames[] = {static_cast<uint32_t>(words)...};
            tensor_pages = frames[0];
            for (uint32_t i = 0; i < kDirFrameMax; ++i) {
                bases[i] = frames[1 + i];
            }
            items = item_count;
            if (tensor_pages == 0 || tensor_pages % kPlanes != 0 ||
                items > kDirMaxItems) {
                return bad(writer, command, kWhereBadSend);
            }
            return true;
        }

        // Writes sent within the run's wait limit (false: gave up, recorded).
        template <typename Writer>
        bool sent(const Writer& writer, const km_command_t& command) {
            const uint32_t code = writer.poll(
                [] {
                    return ncrisc_noc_nonposted_writes_sent(noc_index);
                },
                writer.args().wait_limit
            );
            if (code == km::kGaveNone) {
                return true;
            }
            writer.gave_up(km::kStWriter, code, kWhereFlush, 0, command.sequence);
            return false;
        }

        // Item `id`'s planes into the frame's pages: whole pages by the page calls, a
        // band by its rows' bytes. -1: go on; else the command's result.
        template <typename Frame, typename Writer>
        int item(const Writer& writer, const km_command_t& command, uint32_t id) {
            const bool is_empty = (id & kItemEmpty) != 0;
            const uint32_t asked = km::wall();
            if (!is_empty && !writer.wait_front(out, kPlanes)) {
                return 1;
            }
            if (!is_empty &&
                get_read_ptr(out) + kPlanes * kOutPageBytes >
                    get_local_cb_interface(out).fifo_limit) {
                return bad(writer, command, kWhereBadSend);
            }
            const uint32_t ready = km::wall();
            const uint32_t page = (id & kItemSlot) * kPlanes;
            if (page / tensor_pages >= kDirFrameMax) {
                return bad(writer, command, kWhereBadSend);
            }
            const uint32_t first_row = id >> kItemRow0Shift & kItemRowMask;
            const uint32_t end_row = id >> kItemRow1Shift & kItemRowMask;
            const uint32_t byte_offset = first_row * kRowBytes;
            const uint32_t bytes =
                (end_row > 0 ? (end_row - first_row) * kRowBytes : kOutPageBytes);
            uint32_t source = (is_empty ? empty : get_read_ptr(out)) + byte_offset;
            if (bytes == kOutPageBytes) {  // whole pages: the page calls
                const Frame frame(bases[page / tensor_pages]);
                for (uint32_t plane = 0; plane < kPlanes; ++plane) {
                    if (!km::write_pages(
                            writer,
                            command,
                            frame,
                            (page + plane) % tensor_pages,
                            1,
                            source
                        )) {
                        return 0;
                    }
                    source += kOutPageBytes;
                }
            } else if constexpr (Frame::kLocal) {  // a band: part of each page, by
                                                   // address
                for (uint32_t plane = 0; plane < kPlanes; ++plane) {
                    const InterleavedAddrGen<true> frame_tensor = {
                        .bank_base_address = bases[(page + plane) / tensor_pages],
                        .page_size = kOutPageBytes
                    };
                    noc_async_write(
                        source,
                        get_noc_addr(
                            (page + plane) % tensor_pages, frame_tensor, byte_offset
                        ),
                        bytes
                    );
                    source += kOutPageBytes;
                }
            } else {  // a band over islands: part of each page, wherever its island is
                const Frame frame(bases[page / tensor_pages]);
                for (uint32_t plane = 0; plane < kPlanes; ++plane) {
                    if (!km::put_bytes(
                            writer,
                            command,
                            frame,
                            (page + plane) % tensor_pages,
                            byte_offset,
                            bytes,
                            source
                        )) {
                        return 0;
                    }
                    source += kOutPageBytes;
                }
                if (!km::put_wait(writer, command)) {
                    return 0;
                }
            }
            if (!sent(writer, command)) {
                return 0;
            }
            if (!is_empty) {
                cb_pop_front(out, kPlanes);
            }
            wait += ready - asked;
            write += km::wall() - ready;
            return -1;
        }

        // The profile item (the pack thread's words): the reader's words (from
        // `handed`, mover A's page, if it came) and the writer's, then the page to
        // this core's page of the profiles. False: the command's end.
        template <typename Profiles, typename Writer>
        bool profile(
            const Writer& writer,
            const km_command_t& command,
            uint32_t profile_address,
            uint32_t handed
        ) {
            if (!writer.wait_front(out, kPlanes)) {
                return true;
            }
            if (get_read_ptr(out) + kPlanes * kOutPageBytes >
                get_local_cb_interface(out).fifo_limit) {
                return bad(writer, command, kWhereBadSend);
            }
            invalidate_l1_cache();
            volatile tt_l1_ptr uint32_t* words = km::l1(get_read_ptr(out));
            if (cb_pages_available_at_front(handed, 1)) {
                volatile tt_l1_ptr uint32_t* reader = km::l1(get_read_ptr(handed));
                for (uint32_t word = 0; word < 4; ++word) {
                    words[kProfReader + word] = reader[word];
                }
                cb_pop_front(handed, 1);
            }
            words[kProfWriter + 0] = wait;
            words[kProfWriter + 1] = write;
            words[kProfWriter + 2] = km::wall() - started;
            words[kProfWriter + 3] = items;
            if (!km::write_pages(
                    writer,
                    command,
                    Profiles(profile_address),
                    writer.me(),
                    1,
                    get_read_ptr(out)
                ) ||
                !sent(writer, command)) {
                return false;
            }
            cb_pop_front(out, kPlanes);
            return true;
        }
    };

    // Mover A's clock for the profile: the command's start, the list's first move.
    struct ReaderClock {
        uint32_t started = km::wall();
        uint32_t moving = 0;

        void move() {
            moving = km::wall();
        }

        // The reader's words (wait, read, total, pages) to the writer through
        // `handed`, when a page of it is free; `cycles` the moves' own.
        void hand(uint32_t handed, uint32_t cycles, uint32_t pages) const {
            const uint32_t span = km::wall() - moving;
            if (!cb_pages_reservable_at_back(handed, 1)) {
                return;
            }
            cb_reserve_back(handed, 1);
            volatile tt_l1_ptr uint32_t* words = km::l1(get_write_ptr(handed));
            words[0] = span - cycles;
            words[1] = cycles;
            words[2] = km::wall() - started;
            words[3] = pages;
            cb_push_back(handed, 1);
        }
    };

}  // namespace fill_k
