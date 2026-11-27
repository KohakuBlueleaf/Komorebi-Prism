/* The near tile step's words of a view's frame's page, from the near tile unit's
 * numbers. */
#include "near_tile_frame_words.h"

uint32_t near_tile_frame_words(
    dr_frame_t* frame, const dr_view_t* view, uint32_t* page
) {
    if (view->kind == DR_VIEW_DEPTH) {
        return 0;
    }
    page[PRISM_TF_NEAR_TILE_LIGHT] = dr_number(
        frame, DR_INDIRECT_NEAR_TILE_N_NEAR_LIGHT
    );
    page[PRISM_TF_NEAR_TILE_UPSAMPLE] = dr_number(
        frame, DR_INDIRECT_NEAR_TILE_N_NEAR_UPSAMPLE
    );
    page[PRISM_TF_NEAR_TILE_ON] = page[PRISM_TF_NEAR_TILE_LIGHT] != 0 &&
        page[PRISM_TF_NEAR_TILE_UPSAMPLE] != 0 &&
        dr_number(frame, DR_INDIRECT_NEAR_TILE_N_NEAR_ON) != 0;
    return 0;
}
