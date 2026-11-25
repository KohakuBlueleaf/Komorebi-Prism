// SHADE on mover A: the directory and the table, then one polled step at a time: the
// pack thread's asks served first, the list pages, each item's planes; until its end.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/texel_pages/space.hpp"

#include "items.hpp"

namespace shade_k {

    // SHADE on mover A: the directory's list pages and items' planes, the textures'
    // pages the pack thread asks for into the slots; false: gave up.
    template <
        typename Directories,
        typename Lists,
        typename Textures,
        typename TableTensor,
        typename Profiles,
        typename Surface>
    inline bool shade_reader(
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
        static_cast<void>(profile);
        static_cast<void>(mode);
        const uint32_t rank = movement.me() - km::first(command);
        Directory words;
        bool valid = false;
        // lit: the surface's frame words (merging reads the opaque layer's surface)
        if (camera != 0) {
            if (!words.read_surface(
                    movement, surface.word, rank, get_write_ptr(kDirA), valid
                )) {
                return false;
            }
            if (!valid) {
                return true;  // the pack thread waits for the table and gives up
            }
        }
        if (!words.read(
                movement, directory.word, opaque, rank, get_write_ptr(kDirA), valid
            )) {
            return false;
        }
        if (!valid) {
            return true;  // the pack thread finds the same from its list and gives up
        }
        if (!push_table(movement, table.word, camera, grid)) {
            return false;
        }
        Items items{words, lists.word, opaque, camera != 0};
        const InterleavedAddrGen<true> pages = {
            .bank_base_address = textures.word, .page_size = kTexPageBytes
        };
        const texel_pages::AskBuffers asks = {
            kFieldTexelAsks,
            kFieldTexelDones,
            texel_space::texel_slots(get_write_ptr(kFieldCommandSpace))
        };
        bool ended = false, failed = false;
        // One step at a time, asks first: true once the pack thread's end has come.
        auto step = [&]() -> bool {
            switch (texel_pages::serve_ask(movement, asks, pages)) {
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
            const int listed = items.list_page(movement);
            if (listed != 0) {
                failed = listed < 0;
                return failed;
            }
            if (!items.planes(movement)) {
                failed = true;
                return true;
            }
            return false;
        };
        const uint32_t code = movement.poll(step, movement.args().wait_limit);
        if (code != km::kGaveNone || failed || !ended) {
            movement.gave_up(
                km::kStReader,
                code != km::kGaveNone ? code : fill_k::kGaveBadItem,
                kWhereShadeReader,
                0,
                command.sequence
            );
            return false;
        }
        return true;
    }

}  // namespace shade_k
