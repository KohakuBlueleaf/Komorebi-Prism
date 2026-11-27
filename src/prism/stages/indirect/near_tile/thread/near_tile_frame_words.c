/* The near tile step's words of a view's frame's page, from the near tile unit's
 * numbers. */
#include "near_tile_frame_words.h"

uint32_t near_tile_frame_words(
    dr_frame_t* frame, const dr_view_t* view, uint32_t* page
) {
    if (view->kind == DR_VIEW_DEPTH) {
        return 0;
    }
    page[PRISM_TF_NEAR_TILE_WEIGHTS] = dr_number(
        frame, DR_INDIRECT_NEAR_TILE_N_NEAR_WEIGHTS
    );
    page[PRISM_TF_NEAR_TILE_OPERAND] = dr_number(
        frame, DR_INDIRECT_NEAR_TILE_N_NEAR_OPERAND
    );
    page[PRISM_TF_NEAR_TILE_UPSAMPLE] = dr_number(
        frame, DR_INDIRECT_NEAR_TILE_N_NEAR_UPSAMPLE
    );
    page[PRISM_TF_NEAR_TILE_HALF] = dr_number(frame, DR_INDIRECT_NEAR_TILE_N_NEAR_HALF);
    page[PRISM_TF_NEAR_TILE_ON] = page[PRISM_TF_NEAR_TILE_WEIGHTS] != 0 &&
        page[PRISM_TF_NEAR_TILE_OPERAND] != 0 &&
        page[PRISM_TF_NEAR_TILE_UPSAMPLE] != 0 &&
        dr_number(frame, DR_INDIRECT_NEAR_TILE_N_NEAR_ON) != 0;
    return 0;
}
