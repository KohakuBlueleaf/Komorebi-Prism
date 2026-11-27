// What a thread in the handler `work` is given: its descriptor decoded (a tile's
// record, a range of triangle blocks), a layer's list span, and the context of the CPU
// that runs it. Included by the generated program after its constants (kFrame*).
#pragma once

#include <stdint.h>

#include "frame.h"
#include "komorebi/device/movement/km_movement.hpp"

namespace prism_frame {

    // The list stream's halves and pattern (compute takes block k of a layer's stream
    // from km::block_half(kListPair, kListPattern, k)).
    constexpr km::BufferPair kListPair = {kFieldFrameListA, kFieldFrameListB};
    constexpr km::Pattern kListPattern = km::kPatternAB;
    static_assert(FL_CHUNK_BLOCKS % km::kPatternAB.length == 0);

    // A tile thread: its record's words, decoded (slots absolute).
    struct Tile {
        uint32_t number;  // its record's number in the tile pull
        uint32_t word;    // the pull's word (TA_CODE, TA_HINT)
        uint32_t sequence;
        uint32_t tile, first_row, end_row;
        uint32_t weight, layers, page;
        uint32_t slot[TR_LAYERS];
        uint32_t entries[TR_LAYERS];
    };

    // A range of a layer's triangle blocks (the count and place pulls).
    struct Range {
        uint32_t number;  // the range's number in the pull
        uint32_t layer;
        uint32_t first_block;
        uint32_t blocks;
        uint32_t sequence;
    };

    // A layer's part of a list pass: its pages [first_page, first_page + pages) of the
    // layer's list, `skip` slots before the tile's first, `blocks` blocks of the
    // stream.
    struct ListSpan {
        uint32_t first_page, pages, skip, entries, blocks;
    };

    inline ListSpan span_of(uint32_t slot, uint32_t entries) {
        if (entries == 0) {
            return {0, 0, 0, 0, 0};
        }
        const uint32_t skip = slot % kFrameSlotsPerPage;
        const uint32_t
            pages = ((skip + entries + kFrameSlotsPerPage - 1) / kFrameSlotsPerPage);
        return {
            slot / kFrameSlotsPerPage,
            pages,
            skip,
            entries,
            (pages + kFrameBlockPages - 1) / kFrameBlockPages
        };
    }

    // A descriptor's tile (FD_KIND TP_TILE).
    template <typename Words>
    inline Tile tile_of(const Words& d) {
        const uint32_t* record = &d[FD_RECORD];
        Tile tile = {
            d[FD_NUMBER],
            d[FD_WORD],
            d[FD_SEQUENCE],
            TR_TILE(record[0]),
            TR_FIRST_ROW(record[0]),
            TR_END_ROW(record[0]),
            record[1],
            record[2],
            record[3],
            {},
            {}
        };
        for (uint32_t layer = 0; layer < TR_LAYERS; layer++) {
            tile.slot[layer] = record[TR_LAYER_SLOT(layer)];
            tile.entries[layer] = record[TR_LAYER_ENTRIES(layer)];
        }
        return tile;
    }

    // A descriptor's range (FD_KIND TP_COUNT or TP_PLACE).
    template <typename Words>
    inline Range range_of(const Words& d) {
        return {
            d[FD_NUMBER], d[FD_LAYER], d[FD_FIRST_BLOCK], d[FD_BLOCKS], d[FD_SEQUENCE]
        };
    }

    // A page word of a layer (TF_L_*).
    template <typename Page>
    inline uint32_t layer_word(const Page& page, uint32_t layer, uint32_t word) {
        return page[TF_LAYER_AT + layer * TF_LAYER_WORDS + word];
    }

    // The view's kind (TV_COLOUR, TV_DEPTH).
    template <typename Page>
    inline uint32_t view_kind(const Page& page) {
        return page[TF_VIEW] >> 8;
    }

#if !defined(COMPILE_FOR_TRISC)
    // A mover's context: its runtime, the command, the frame's page (the command's
    // block), the handler's memory, the regions' bank, the core's rank in the
    // command's group and the group's cores.
    struct MoverContext {
        km::Movement& movement;
        const km_command_t& command;
        const volatile tt_l1_ptr uint32_t* page;
        uint32_t memory;  // the command space's part frame_memory: its L1 address
        uint32_t bank;    // the X280 thread's regions' bank
        uint32_t rank;
        uint32_t cores;

        uint32_t word(uint32_t index) const {
            return page[index];
        }

        uint32_t layer(uint32_t layer, uint32_t word) const {
            return layer_word(page, layer, word);
        }

        // Kept state at its byte (a kKept* of the generated program).
        uint32_t kept(uint32_t at) const {
            return memory + kFrameKeptAt + at;
        }

        // A give-up of this mover at `where`.
        bool gave_up(uint32_t code, uint32_t where) const {
            movement.gave_up(
                km::kMover == km::kMoverA ? km::kStReader : km::kStWriter,
                code,
                where,
                km::slot(command),
                command.sequence
            );
            return false;
        }
    };
#else
    // A compute CPU's context: its runtime, the command, the frame's page (mover A's
    // copy), the handler's memory, the core's rank in the command's group and the
    // group's cores and, on pack, the ask's turn, the output turns and blocks by half.
    struct ComputeContext {
        km::Compute& compute;
        const km_command_t& command;
        const volatile uint32_t* page;
        uint32_t memory;
        uint32_t rank;
        uint32_t cores;
        uint32_t ask_turn;
        uint32_t out_turn[kFrameOutputs + 1];
        uint32_t out_blocks[2];

        uint32_t word(uint32_t index) const {
            return page[index];
        }

        uint32_t layer(uint32_t layer, uint32_t word) const {
            return layer_word(page, layer, word);
        }

        uint32_t kept(uint32_t at) const {
            return memory + kFrameKeptAt + at;
        }

        uint32_t planes() const {
            return memory + kFramePlanesAt;
        }
    };
#endif

    // A kind's context: the CPU's, with `Buffers` its rings' indices by the names its
    // Kind declares (generated).
#if !defined(COMPILE_FOR_TRISC)
    template <typename B>
    struct KindContext : MoverContext {
        using Buffers = B;
    };
#else
    template <typename B>
    struct KindContext : ComputeContext {
        using Buffers = B;
    };
#endif

}  // namespace prism_frame
