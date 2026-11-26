/* What a core is handed and what it tells: shared by the frame's thread (C) and the
 * kernels (C++). A pull hands a core one number and, in the tile pull, one word. */
#pragma once

#include <stdint.h>

/* The pull a command is (the frame's page word TF_PULL): what its numbers mean */
#define TP_COUNT 1u /* a range of a layer's triangle blocks, counted */
#define TP_PLACE 2u /* the ranges a core counted, again: placed into the lists */
#define TP_TILE 3u  /* a tile thread: the number of its record */

/* The tile pull's word: code | hint << TA_HINT_SHIFT.
 * code: which variant of the tile thread's code runs (0: the resident one).
 * hint: the answer's note to the core (TA_HINT_*). */
#define TA_CODE_MASK 0xFFu
#define TA_HINT_SHIFT 8u
#define TA_HINT_NEAR 1u /* near the core's last tile: its pages may be held */
#define TA_WORD(code, hint) ((uint32_t)(code) | (uint32_t)(hint) << TA_HINT_SHIFT)
#define TA_CODE(word) ((word) & TA_CODE_MASK)
#define TA_HINT(word) ((word) >> TA_HINT_SHIFT)

/* What a core tells with an ask (three words): the number of the thread that ended
 * (TA_NONE_ENDED: none since the last tell), its cost (timer cycles >> TA_COST_SHIFT),
 * the codes it holds (a bit a code). */
#define TA_TELL_WORDS 3u
#define TA_NONE_ENDED 0xFFFFFFFFu
#define TA_COST_SHIFT 10u
