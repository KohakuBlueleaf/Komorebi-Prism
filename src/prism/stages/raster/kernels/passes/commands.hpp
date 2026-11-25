// COUNT's and SETUP's work on each CPU as one call from a class body: the command's
// words and buffers gathered for the reader, the compute threads and the writer.
#pragma once

#include <stdint.h>

#include "../common/profile.hpp"
#include "read.hpp"
#include "count.hpp"
#include "lists.hpp"

namespace setup_k {

    // COUNT's writer: the counting, then the profile's 128 bytes. -1: the costs are
    // to be put after it (a first COUNT); 1: done, no costs (the recount keeps the
    // first COUNT's counters and costs); 0: failed.
    template <typename Writer, typename Region>
    int count_write(
        const Writer& writer,
        CountWords words,
        const Region& heavy,
        uint32_t profile,
        uint32_t profile_address
    ) {
        const uint32_t started = km::wall();
        words.heavy_bank = bank_of(heavy);
        words.heavy_address = heavy.word;
        WriterProfile counted;
        if (!count_stage(writer, words, counted) ||
            !send_profile(
                writer,
                get_write_ptr(profile),
                profile_address,
                kHandlerCount,
                counted,
                started
            )) {
            return 0;
        }
#ifdef RASTER_RECOUNT
        if (words.heavy_address != 0) {
            return 1;
        }
#endif
        return -1;
    }

    // SETUP's reader: the next slots and the items table, pushed to the
    // writer before the lines read the camera's page and the blocks.
    template <typename Reader, typename Region>
    void setup_slots(
        const Reader& reader,
        const SlotWords& slot_words,
        const Region& items,
        uint32_t grid
    ) {
        read_slots(reader, ReadWords{bank_of(items), grid}, slot_words);
    }

    // SETUP's writer: the records to their slots, then the profile.
    template <typename Writer>
    bool setup_write(
        const Writer& writer,
        const ListWords& words,
        uint32_t profile,
        uint32_t profile_address
    ) {
        const uint32_t started = km::wall();
        WriterProfile listed;
        if (!setup_stage(writer, words, listed)) {
            return false;
        }
        return send_profile(
            writer,
            get_write_ptr(profile),
            profile_address,
            kHandlerSetup,
            listed,
            started
        );
    }

}  // namespace setup_k
