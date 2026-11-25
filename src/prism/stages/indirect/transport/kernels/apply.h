// The apply y = M x on every core: a table page's and an entry's words, the reads'
// pattern, and the helpers the three roles share.
#pragma once

#include <stdint.h>

namespace apply_k {

    // mover B's table page and head page: the common own pages
    constexpr uint32_t kTableB = kFieldOwnPage1;
    constexpr uint32_t kHeadB = kFieldOwnPage2;

    // A table page (plan/tables.py): word 0 its entries, 1 and 2 the core's first own
    // tile and their count; entries of 8 words from word 8, at most 127 a page.
    constexpr uint32_t kHead = 8;
    constexpr uint32_t kEntryWords = 8;
    constexpr uint32_t kEntriesMost = 127;
    constexpr uint32_t kHeadFirst = 1;
    constexpr uint32_t kHeadOwn = 2;
    // An entry's words: x's tiles src : src + k, the first stream's pages w : w + a,
    // U^T's u : u + b, the first own receiver r, R tiles of rank (0: dense).
    constexpr uint32_t kSrc = 0;
    constexpr uint32_t kK = 1;
    constexpr uint32_t kW = 2;
    constexpr uint32_t kA = 3;
    constexpr uint32_t kU = 4;
    constexpr uint32_t kB = 5;
    constexpr uint32_t kR = 6;
    constexpr uint32_t kRankWord = 7;
    // Pack's own-tile mask: a bit an own sums tile, in as many words as kConstOwn
    // needs.
    constexpr uint32_t kOwnWords = (kConstOwn + 31) / 32;
    // The reads' pattern: mover B every fourth block.
    constexpr km::Pattern kReadPattern = km::pattern("AAAB");

    // The entries of a table page (none when its count word is past a page's room).
    inline uint32_t entries(const volatile tt_l1_ptr uint32_t* page) {
        return page[0] <= kEntriesMost ? page[0] : 0;
    }

    // Entry `at` of a table page.
    inline const volatile tt_l1_ptr uint32_t* entry(
        const volatile tt_l1_ptr uint32_t* page, uint32_t at
    ) {
        return page + kHead + kEntryWords * at;
    }

}  // namespace apply_k
