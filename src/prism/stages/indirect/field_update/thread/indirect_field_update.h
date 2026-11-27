/* The field update's numbers shared by its C and model/numbers.py: the sizes, the times
 * row's words, the steps and the codes. The header region's word places are the build's
 * FU_H_* defines (model/numbers.py), its regions and numbers the layout's macros. */
#pragma once

#include "director.h"

#define FU_SKY_TERMS 25u      /* the sky's terms, three colours each */
#define FU_PAGE_TEXELS 1024u  /* a light page's 32-bit texels */
#define FU_PAGE_BYTES 4096u   /* a light page */
#define FU_X_PAGE_BYTES 2048u /* x's page: a bf16 tile */
#define FU_Y_PAGE_BYTES 4096u /* y's page: a float32 tile */
#define FU_ALIGN 4096u /* each array of the elements and work regions on its pages */
#define FU_TILE 32u

/* The times region: update k's row at row k % FU_TIMES_ROWS, ticks of each part summed
 * over its steps */
#define FU_TIMES_ROWS 16u
#define FU_T_FETCH 0u   /* the shadow map's pages fetched */
#define FU_T_SOURCES 1u /* sun, sky, L0 and pass 1's x */
/* pass p: x stored, the apply, y fetched, the total and the next x; a pass after the
 * last the row tells apart adds into that one's words */
#define FU_T_PASS 2u
#define FU_T_PASS_WORDS 4u
#define FU_T_PASS_APART 3u /* the passes the times row tells apart */

#define FU_T_ROWS 14u   /* the field's values by row */
#define FU_T_PACK 15u   /* the scale, the texels into the pages */
#define FU_T_STORE 16u  /* the pages stored into the field's tensor */
#define FU_T_TABLE 17u  /* LIGHT's words: none in this unit, 0 */
#define FU_T_TOTAL 18u  /* the commands of the update, call to answer, summed */
#define FU_T_NUMBER 19u /* updates finished before it: its row */
#define FU_T_CODE 20u   /* the last command's answer */
#define FU_T_STEP 21u   /* the last step */
#define FU_T_PASSES 22u /* passes taken */
#define FU_T_SCALE 23u  /* float: the field's scale */
#define FU_T_ZERO 24u   /* the pages zeroed (the first update only), part of PACK */
#define FU_T_UNIT 25u   /* float x 3: LIGHT's units, (1 / max code)^2 x scale */
#define FU_T_BEGAN 28u  /* job form: the timer's low word, sources' start */
#define FU_T_ENDED 29u  /* job form: the timer's low word, finish's end */
#define FU_T_WORDS 32u

/* UPDATE's a0: the step */
#define FU_STEP_ALL 0u     /* the whole update, each pass's apply on the cores */
#define FU_STEP_SOURCES 1u /* the sources, through pass 1's x stored */
#define FU_STEP_PASS 2u    /* y fetched, added; the next x stored while passes remain */
#define FU_STEP_FINISH 3u  /* the field and its pages */

/* The unit's codes: the words or regions do not hold the update, or a step out of turn;
 * a fetch or a store did not finish */
#define FU_BAD_UPDATE (DR_UNIT_CODES + 1u)
#define FU_COPY (DR_UNIT_CODES + 2u)
