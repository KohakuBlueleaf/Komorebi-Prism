/* The depth_out step's words of a DEPTH view's frame's page, its target's pages. */
#include "depth_out_frame_words.h"

uint32_t depth_out_frame_words(
    dr_frame_t* frame, const dr_view_t* view, uint32_t* page
) {
    (void)frame;
    if (view->kind != DR_VIEW_DEPTH) {
        return 0;
    }
    if (view->target_pages == 0) {
        return DR_BAD_ARGS;
    }
    page[PRISM_TF_DEPTH_OUT_PAGES] = view->target_pages;
    page[PRISM_TF_DEPTH_OUT_LEVELS] = view->levels;
    page[PRISM_TF_DEPTH_OUT_LEVELS_SHIFT] = view->levels_shift;
    page[PRISM_TF_DEPTH_OUT_TOPS] = view->tops;
    return 0;
}
