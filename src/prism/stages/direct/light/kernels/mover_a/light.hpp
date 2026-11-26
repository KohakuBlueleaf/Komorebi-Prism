// LIGHT on mover A: the directories, the table page, then one step at a time the pack
// CPU's asks first, else the next item's planes and word, until the pack CPU's end.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/texel_pages/space.hpp"

#include "../../../../../core/include/texel_pages/ask.hpp"
#include "directories.hpp"
#include "items.hpp"
#include "table.hpp"

namespace light_k {

    // The buffers LIGHT's mover A uses: its directory page, the table page, the items'
    // words, the planes ring, the asks' (ask, done, slots).
    struct ReaderBuffers {
        uint32_t directory, table, items, planes;
        texel_pages::AskBuffers asks;
    };

    // LIGHT of one command on mover A (`mode` its form, kLight*). False: gave up or a
    // directory unsound.
    template <typename Mover, typename Directory, typename Glass, typename Surface>
    bool read_command(
        const Mover& reader,
        const km_command_t& command,
        const ReaderBuffers& buffers,
        const Directory& directory_tensor,
        const Glass& glass_tensor,
        const Surface& surface_tensor,
        const TableWords& table_words,
        uint32_t mode
    ) {
        const uint32_t scratch = get_write_ptr(buffers.directory);
        volatile tt_l1_ptr uint32_t* directory = km::l1(scratch);
        SurfaceWords surface;
        if (!surface_words(reader, command, surface_tensor, scratch, surface)) {
            return false;
        }
        const bool glass = mode == kLightGlass;
        uint32_t glass_frame[kDirFrameMax + 1] = {};  // the glass layer's frame words
        if (glass &&
            !glass_words(reader, command, glass_tensor, scratch, glass_frame)) {
            return false;
        }
        const uint32_t item_pages = glass ? kLightGlassPages : kLightItemPages;
        if (!read_directory(reader, command, directory_tensor, scratch)) {
            return false;
        }
        const uint32_t items = directory[kDirItems];
        if (!items_sound(directory)) {
            return true;  // the pack CPU waits for its table and gives up
        }
        if (!read_table(reader, command, table_words, surface, buffers.table)) {
            return false;
        }
        const InterleavedAddrGen<true> light_pages = {
            .bank_base_address = surface.pages(), .page_size = kTexPageBytes
        };
        const ItemSources from = {
            surface, directory, glass_frame, glass, buffers.planes, buffers.items
        };
        uint32_t item = 0;
        bool ended = false, failed = false;
        // One step at a time, asks first: true once the pack CPU's end has come.
        auto step = [&]() -> bool {
            switch (texel_pages::serve_ask(reader, buffers.asks, light_pages)) {
                case texel_pages::kAskEnd:
                    ended = true;
                    return true;
                case texel_pages::kAskFailed:
                    failed = true;
                    return true;
                case texel_pages::kAskServed:
                case texel_pages::kAskBlocked:
                    return false;
                case texel_pages::kAskNone:
                    break;
            }
            if (item > items || !cb_pages_reservable_at_back(buffers.items, 1)) {
                return false;
            }
            if (item == items) {  // the end's word
                cb_reserve_back(buffers.items, 1);
                *km::l1(get_write_ptr(buffers.items)) = kShadeAskEnd;
                cb_push_back(buffers.items, 1);
                ++item;
                return false;
            }
            if (!cb_pages_reservable_at_back(buffers.planes, item_pages)) {
                return false;
            }
            if (!read_item(reader, command, from, item)) {
                failed = true;
                return true;
            }
            ++item;
            return false;
        };
        const uint32_t code = reader.poll(step, reader.args().wait_limit);
        if (code != km::kGaveNone || failed || !ended) {
            reader.gave_up(
                km::kStReader,
                code != km::kGaveNone ? code : fill_k::kGaveBadItem,
                kWhereLightReader,
                0,
                command.sequence
            );
            return false;
        }
        return true;
    }

    // The handler's mover A: its buffers by the class's header, its words.
    template <typename Mover, typename Directory, typename Glass, typename Surface>
    inline bool light_reader(
        Mover& movement,
        const km_command_t& command,
        const Directory& directory,
        uint32_t table,
        uint32_t shade_table,
        uint32_t camera,
        const Glass& glass,
        const Surface& surface,
        uint32_t bank_grid,
        uint32_t mode
    ) {
        const ReaderBuffers buffers = {
            kFieldReaderPage,
            kFieldFrameTable,
            kFieldItems,
            kFieldInPlanes,
            {kFieldTexelAsks,
             kFieldTexelDones,
             texel_space::texel_slots(get_write_ptr(kFieldCommandSpace))}
        };
        const uint32_t form = mode & ~kLightShown;
        const TableWords words = {
            table, camera, bank_grid, shade_table, form == kLightGlass
        };
        return read_command(
            movement, command, buffers, directory, glass, surface, words, form
        );
    }

}  // namespace light_k
