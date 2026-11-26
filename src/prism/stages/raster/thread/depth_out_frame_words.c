/* The depth_out step's words of a DEPTH view's frame's page, from the view's target. */
#include "depth_out_frame_words.h"

#include "../../../core/include/thread/frame.h"

uint32_t depth_out_frame_words(
    dr_frame_t* frame, const dr_view_t* view, uint32_t* page
) {
    (void)frame;
    if (view->kind != DR_VIEW_DEPTH) {
        return 0;
    }
    if (view->target == 0 || view->target_across == 0 ||
        view->target_first >= view->target_pages) {
        return DR_BAD_ARGS;
    }
    page[PRISM_TF_DEPTH_OUT_FIRST] = view->target_first;
    page[PRISM_TF_DEPTH_OUT_ACROSS] = view->target_across;
    page[PRISM_TF_DEPTH_OUT_PAGES] = view->target_pages;
    page[TF_TARGET] = view->target;
    return 0;
}
