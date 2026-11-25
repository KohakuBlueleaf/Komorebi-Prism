// SHOW's and COPY's item write on mover B: each item's planes from the planes buffer
// converted (or copied) into a scratch page, its rows written to its display page.
#pragma once

#include <stdint.h>

#include "../../../raster/kernels/common/layouts.hpp"
#include "api/dataflow/dataflow_api.h"
#include "convert.hpp"
#include "komorebi/device/km_worker.hpp"
#include "space.hpp"

namespace show_k {
#include "show.h"

    using fill_k::kDirFrameMax;
    using fill_k::kDirMaxItems;
    using fill_k::kGaveBadItem;
    using fill_k::kItemRow0Shift;
    using fill_k::kItemRow1Shift;
    using fill_k::kItemRowMask;
    using fill_k::kItemSlot;
    using fill_k::kPlanes;
    using fill_k::kRowBytes;
    using fill_k::kWhereFlush;

    // Mover B's state for one command: the planes buffer and the scratch pages, the
    // thresholds and buckets, the target's pages, its cycles and counts.
    struct Writer {
        uint32_t planes = 0, scratch = 0;
        uint32_t started = km::wall();
        uint32_t convert = 0, wait = 0, write = 0, rows = 0, items = 0, done = 0;
        uint32_t tensor_pages = 0;
        int32_t thresholds[kShowTableWords] = {};

        // The command's buffers: the planes from mover A, the scratch pages (L1).
        void start(uint32_t buffer, uint32_t scratch_pages) {
            planes = buffer;
            scratch = scratch_pages;
        }

        tt_l1_ptr uint8_t* buckets() const {
            return reinterpret_cast<tt_l1_ptr uint8_t*>(
                scratch + kShowBucketsPage * kShowPageBytes
            );
        }

        // The thresholds from the table's field (L1) and their buckets.
        void table(uint32_t field) {
            thresholds_of(field, thresholds, buckets());
        }

        // A bad table or item, recorded by the writer.
        template <typename Writer_>
        bool bad(const Writer_& writer, const km_command_t& command) const {
            writer.gave_up(
                km::kStWriter, kGaveBadItem, kWhereShowBad, 0, command.sequence
            );
            *writer.control(KM_CONTROL_STOP) = 1;
            return false;
        }

        // The directory's items and pages a frame tensor; false: not a frame
        // (recorded).
        template <typename Writer_>
        bool frame(
            const Writer_& writer,
            const km_command_t& command,
            uint32_t item_count,
            uint32_t pages
        ) {
            items = item_count;
            tensor_pages = pages;
            if (tensor_pages == 0 || tensor_pages % kPlanes != 0 ||
                items > kDirMaxItems) {
                return bad(writer, command);
            }
            return true;
        }

        // Writes sent within the run's wait limit (false: gave up, recorded).
        template <typename Writer_>
        bool sent(const Writer_& writer, const km_command_t& command) const {
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

        // Item `id` to page first + (tile / 32) across + tile mod 32
        // of `target` (`pages` of it): colour converted, or (`raw`) plane 0 as it
        // is. -1: go on; else the command's result.
        template <typename Writer_>
        int item(
            const Writer_& writer,
            const km_command_t& command,
            uint32_t id,
            uint32_t target,
            uint32_t first,
            uint32_t across,
            uint32_t pages,
            bool raw
        ) {
            const uint32_t tile = id & kItemSlot;
            const uint32_t page = first + tile / kGridDefault * across +
                tile % kGridDefault;
            if ((tile * kPlanes) / tensor_pages >= kDirFrameMax || page >= pages) {
                return bad(writer, command);
            }
            const uint32_t first_row = id >> kItemRow0Shift & kItemRowMask;
            const uint32_t row_end = id >> kItemRow1Shift & kItemRowMask;
            const uint32_t end_row = row_end > 0 ? row_end : 32;
            const uint32_t byte_offset = first_row * kRowBytes;
            const uint32_t asked = km::wall();
            if (!writer.wait_front(planes, kShowPlanes)) {
                return 1;
            }
            const uint32_t out = scratch + (done++ & 1) * kShowPageBytes;
            if (!sent(writer, command)) {  // the page's last write left
                return 0;
            }
            const uint32_t ready = km::wall();
            invalidate_l1_cache();
            // plain loads and stores: the planes stay put until the pop, the page
            // until its write is sent
            const tt_l1_ptr uint32_t*
                red = (reinterpret_cast<const tt_l1_ptr uint32_t*>(
                    get_read_ptr(planes)
                ));
            tt_l1_ptr uint32_t* pixels = reinterpret_cast<tt_l1_ptr uint32_t*>(out);
            if (raw) {
                plane_rows(red, pixels, first_row, end_row);
            } else {
                colour_rows(red, pixels, first_row, end_row, thresholds, buckets());
            }
            cb_pop_front(planes, kShowPlanes);
            const uint32_t converted = km::wall();
            const InterleavedAddrGen<true> display = {
                .bank_base_address = target, .page_size = kShowPageBytes
            };
            noc_async_write(
                out + byte_offset,
                get_noc_addr(page, display, byte_offset),
                (end_row - first_row) * kRowBytes
            );
            wait += ready - asked;
            convert += converted - ready;
            write += km::wall() - converted;
            rows += end_row - first_row;
            return -1;
        }
    };

}  // namespace show_k
