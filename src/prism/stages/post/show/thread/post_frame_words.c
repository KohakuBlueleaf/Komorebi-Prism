/* The post step's words of a view's frame's page, from the display unit's numbers and
 * its thresholds' region. */
#include "post_frame_words.h"

#include "../../../../core/include/thread/frame.h"

uint32_t post_frame_words(dr_frame_t* frame, const dr_view_t* view, uint32_t* page) {
    if (view->kind == DR_VIEW_DEPTH) {
        return 0;
    }
    const uint32_t display = dr_number(frame, DR_POST_SHOW_N_SHOW_DISPLAY);
    if (display == 0 || view->tiles == 0) {
        return DR_BAD_ARGS;
    }
    page[PRISM_TF_POST_TABLE] = DR_ADDRESS(DR_POST_SHOW_REGION_SHOW_TABLE);
    page[PRISM_TF_POST_PAGES] = view->tiles;
    page[TF_TARGET] = display;
    return 0;
}
