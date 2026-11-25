// HIST on mover B: each heavy tile's 64 bytes of the histograms COUNT kept, to this
// core's page of histograms at the tile's place among the heavy tiles.
#pragma once

#include <stdint.h>

#include "../common/give_up.hpp"
#include "../common/layouts.hpp"
#include "../common/noc.hpp"
#include "../common/profile.hpp"
#include "../common/space.hpp"

namespace setup_k {

    struct HistState {
        uint32_t started = km::wall();  // the command's start, for the profile
        uint32_t histograms = 0;        // the histograms tensor's address
        uint32_t page_bytes = 0;        // its pages' bytes
        uint32_t space = 0;             // the histograms COUNT kept (L1)
        uint32_t heavy_index = 0;       // the next heavy tile's place

        // The command's words: the histograms' address and page bytes, the kept space.
        void start(uint32_t histograms_at, uint32_t bytes, uint32_t kept) {
            histograms = histograms_at;
            page_bytes = bytes;
            space = kept;
        }

        // The heavy tiles' count against the tables and the page (false: gave up).
        bool fits(uint32_t control, uint32_t heavy_count) const {
            if (heavy_count >= kHeavyBytes / 4 || 64 * heavy_count > page_bytes) {
                give_up(control, kGaveBadHeavy, heavy_count);
                return false;
            }
            return true;
        }

        // Heavy tile `tile`'s histogram (RASTER_RECOUNT: the second COUNT's slot).
        template <typename Writer>
        void send(const Writer& writer, uint32_t tile) {
#ifdef RASTER_RECOUNT
            tile = heavy_index;  // the second COUNT's table
#else
            tile %= kTiles;
#endif
            noc_async_write(
                space + 64 * tile,
                noc_address(0, histograms, writer.me(), page_bytes, 64 * heavy_index),
                64
            );
            ++heavy_index;
        }

        // The writes flushed, then the profile page's 128 bytes (address 0: none).
        template <typename Writer>
        bool end(const Writer& writer, uint32_t profile_page, uint32_t profile) const {
            if (!flushed(writer)) {
                return false;
            }
            return send_profile(
                writer, profile_page, profile, kHandlerHist, WriterProfile{}, started
            );
        }
    };

}  // namespace setup_k
