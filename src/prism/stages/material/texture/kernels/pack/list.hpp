// SHADE's list on the pack thread: the core's list slots (items' headers and records),
// page by page from the unpack thread.
#pragma once

#include <stdint.h>

#include "vector.hpp"

namespace shade_k {

    // The list's slots, page by page from the unpack thread.
    struct List {
        const compute_mail::Waits& waits;
        uint32_t page = 0;
        uint32_t slot = kSlotsPerPage;
        uint32_t wait = 0;

        const volatile uint32_t* next() {
            if (slot == kSlotsPerPage) {
                const uint32_t asked = km::wall();
                if (page != 0 && !compute_mail::pop(waits, kFieldShadeLists, 1)) {
                    return nullptr;
                }
                page = compute_mail::front(waits, kFieldShadeLists, 1);
                wait += km::wall() - asked;
                if (page == 0) {
                    return nullptr;
                }
                slot = 0;
            }
            return (
                reinterpret_cast<const volatile uint32_t*>(page) + kSlotWords * slot++
            );
        }

        bool end() {
            return page == 0 || compute_mail::pop(waits, kFieldShadeLists, 1);
        }
    };

}  // namespace shade_k
