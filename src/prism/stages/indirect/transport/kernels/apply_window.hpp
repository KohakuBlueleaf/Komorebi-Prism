// The apply in a frame program (APPLY_WINDOWS): its streams and multi-page fields,
// declared one page each, placed for the command inside the common field command_space,
// which no other handler uses during an apply; each CPU's views set back at its end
// (their places alone: the pages counted stay as the command left them).
#pragma once

#include "apply.h"

namespace apply_k {

#if defined(APPLY_WINDOWS)
    // A window: a buffer, its pages as the class alone declares them, a page's bytes.
    struct Window {
        uint32_t cb;
        uint32_t pages;
        uint32_t page_bytes;
    };

    constexpr uint32_t kWindowAlign = 64;  // a window's start: the movers' reads land
    constexpr Window kWindows[] = {
        {kPairXIn.mover_a, APPLY_PAGES_X_IN, APPLY_BYTES_X_IN},
        {kPairXIn.mover_b, APPLY_PAGES_X_IN, APPLY_BYTES_X_IN},
        {kPairWIn.mover_a, APPLY_PAGES_W_IN, APPLY_BYTES_W_IN},
        {kPairWIn.mover_b, APPLY_PAGES_W_IN, APPLY_BYTES_W_IN},
        {kFieldSums, APPLY_PAGES_SUMS, APPLY_BYTES_SUMS},
        {kFieldT, APPLY_PAGES_T, APPLY_BYTES_T},
        {kFieldToken, APPLY_PAGES_TOKEN, APPLY_BYTES_TOKEN},
        {kFieldYPage, APPLY_PAGES_Y_PAGE, APPLY_BYTES_Y_PAGE},
    };
    constexpr uint32_t kWindowCount = sizeof(kWindows) / sizeof(kWindows[0]);

    // Window `w`'s first byte in the field: the windows end to end, each aligned.
    constexpr uint32_t window_at(uint32_t w) {
        uint32_t at = 0;
        for (uint32_t i = 0; i < w; i++) {
            at += kWindows[i].pages * kWindows[i].page_bytes;
            at = (at + kWindowAlign - 1) / kWindowAlign * kWindowAlign;
        }
        return at;
    }

    constexpr uint32_t kWindowsEnd = window_at(kWindowCount - 1) +
        kWindows[kWindowCount - 1].pages * kWindows[kWindowCount - 1].page_bytes;
    constexpr uint32_t kSpaceBytes = kFieldCommandSpacePages *
        kFieldCommandSpacePageBytes;
    static_assert(kWindowsEnd <= kSpaceBytes, "the apply's windows fit command_space");

    // A view's place: its size, limit, pages and pointers.
    struct Kept {
        uint32_t size;
        uint32_t limit;
        uint32_t pages;
        uint32_t rd;
        uint32_t wr;
        uint32_t wr_tile;
    };

    // This CPU's views of the windows for one command (math keeps none): placed when
    // made, each buffer empty; set back to their places when it ends.
    class Windows {
    public:
        Windows() {
#if !defined(TRISC_MATH)
            const LocalCBInterface& field = get_local_cb_interface(kFieldCommandSpace);
            const uint32_t base = field.fifo_limit - field.fifo_size;
            for (uint32_t w = 0; w < kWindowCount; w++) {
                LocalCBInterface& view = get_local_cb_interface(kWindows[w].cb);
                kept_[w] = {
                    view.fifo_size,
                    view.fifo_limit,
                    view.fifo_num_pages,
                    view.fifo_rd_ptr,
                    view.fifo_wr_ptr,
                    view.fifo_wr_tile_ptr
                };
                const uint32_t start = base + (window_at(w) >> cb_addr_shift);
                view.fifo_size = kWindows[w].pages * view.fifo_page_size;
                view.fifo_limit = start + view.fifo_size;
                view.fifo_num_pages = kWindows[w].pages;
                view.fifo_rd_ptr = start;
                view.fifo_wr_ptr = start;
                view.fifo_wr_tile_ptr = 0;
            }
#endif
        }

        ~Windows() {
#if !defined(TRISC_MATH)
            for (uint32_t w = 0; w < kWindowCount; w++) {
                LocalCBInterface& view = get_local_cb_interface(kWindows[w].cb);
                view.fifo_size = kept_[w].size;
                view.fifo_limit = kept_[w].limit;
                view.fifo_num_pages = kept_[w].pages;
                view.fifo_rd_ptr = kept_[w].rd;
                view.fifo_wr_ptr = kept_[w].wr;
                view.fifo_wr_tile_ptr = kept_[w].wr_tile;
            }
#endif
        }

        Windows(const Windows&) = delete;
        Windows& operator=(const Windows&) = delete;

    private:
#if !defined(TRISC_MATH)
        Kept kept_[kWindowCount];
#endif
    };
#else
    // The apply alone: its buffers are its own, whole.
    class Windows {};
#endif

}  // namespace apply_k
