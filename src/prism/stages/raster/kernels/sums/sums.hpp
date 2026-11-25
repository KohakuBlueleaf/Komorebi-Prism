// SUM and HSUM on the pack thread: a slice's (or a heavy tile's) counts summed over the
// counting cores, each core's exclusive prefix written, then the totals.
#pragma once

#include <stdint.h>

namespace setup_k {

    // SUM: one slice of 16 tiles, its entries and rows summed over the cores so far.
    struct SumState {
        uint32_t entries[16], row_counts[16];

        void zero() {
            for (uint32_t j = 0; j < 16; ++j) {
                entries[j] = row_counts[j] = 0;
            }
        }

        // One core's slice (L1 addresses): its entries' exclusive prefix to `prefix`
        // (0: none), both sums added.
        void add(uint32_t entry, uint32_t row, uint32_t prefix) {
            volatile uint32_t* entry_words = reinterpret_cast<volatile uint32_t*>(
                entry
            );
            volatile uint32_t* row_words = reinterpret_cast<volatile uint32_t*>(row);
            volatile uint32_t* prefix_words = reinterpret_cast<volatile uint32_t*>(
                prefix
            );
            for (uint32_t j = 0; j < 16; ++j) {
                const uint32_t count = entry_words[j];
                if (prefix != 0) {
                    prefix_words[j] = entries[j];
                }
                entries[j] += count;
                row_counts[j] += row_words[j];
            }
            asm volatile("fence" ::: "memory");
        }

        // The slice's totals at `totals` (0: none): entries, then rows 64 bytes on.
        void totals(uint32_t totals) const {
            if (totals == 0) {
                return;
            }
            volatile uint32_t* total_words = reinterpret_cast<volatile uint32_t*>(
                totals
            );
            for (uint32_t j = 0; j < 16; ++j) {
                total_words[j] = entries[j];
                total_words[16 + j] = row_counts[j];
            }
            asm volatile("fence" ::: "memory");
        }
    };

    // HSUM: one heavy tile's 16 starts and 16 ends summed over the cores so far.
    struct HsumState {
        uint32_t totals[32];

        void zero() {
            for (uint32_t i = 0; i < 32; ++i) {
                totals[i] = 0;
            }
        }

        // One core's 32 counts (uint16): the starts' and ends' running sums before it
        // to `prefix` (0: none), then its counts added.
        void add(uint32_t counts, uint32_t prefix) {
            volatile uint16_t* count_words = reinterpret_cast<volatile uint16_t*>(
                counts
            );
            volatile uint32_t* prefix_words = reinterpret_cast<volatile uint32_t*>(
                prefix
            );
            uint32_t starts = 0, ends = 0;
            for (uint32_t i = 0; i < 16; ++i) {
                starts += totals[i];
                ends += totals[16 + i];
                if (prefix != 0) {
                    prefix_words[i] = starts;
                    prefix_words[16 + i] = ends;
                }
            }
            for (uint32_t i = 0; i < 32; ++i) {
                totals[i] += count_words[i];
            }
            asm volatile("fence" ::: "memory");
        }

        // The tile's 32 counts over the cores at `total` (0: none).
        void total(uint32_t total) const {
            if (total == 0) {
                return;
            }
            volatile uint32_t* total_words = reinterpret_cast<volatile uint32_t*>(
                total
            );
            for (uint32_t i = 0; i < 32; ++i) {
                total_words[i] = totals[i];
            }
            asm volatile("fence" ::: "memory");
        }
    };

}  // namespace setup_k
