/* The post step's words of a view's frame's page, from the view's tiles and its
 * thresholds' region. */
#include "post_frame_words.h"

uint32_t post_frame_words(dr_frame_t* frame, const dr_view_t* view, uint32_t* page) {
    (void)frame;
    if (view->kind == DR_VIEW_DEPTH) {
        return 0;
    }
    if (view->tiles == 0) {
        return DR_BAD_ARGS;
    }
    page[PRISM_TF_POST_TABLE] = DR_ADDRESS(DR_POST_SHOW_REGION_SHOW_TABLE);
    page[PRISM_TF_POST_PAGES] = view->tiles;
    return 0;
}
