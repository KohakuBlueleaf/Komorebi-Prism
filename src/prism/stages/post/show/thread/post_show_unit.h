/* The post.show unit: a view's SHOW of the frame (the directory of the frame.visibility
 * it takes) into the display, then, when the host arms it, the display's PUSH to the
 * host; its command words by the generated header's builder and places. */
#pragma once

#include <stdint.h>

#include "director.h"

/* The PUSH's words in its region (session.channel_transfer's entry): the header, the
 * group, a0 to a9, then the frame's key, XORed into the nonce word */
#define SHOW_PUSH_HEADER 0u
#define SHOW_PUSH_GROUP 1u
#define SHOW_PUSH_ARGS 2u
#define SHOW_PUSH_KEY 12u
#define SHOW_PUSH_BYTES 64u
#define SHOW_PUSH_NONCE 7u /* the transfer's nonce word: a7 */

/* A COLOUR view: SHOW of its first layer's frame, then the PUSH (the number
 * show_pushes); a DEPTH view: COPY of its 1/z into its target, no PUSH. 0, or the
 * code. */
uint32_t post_show_unit_frame(dr_frame_t* frame, const dr_view_t* view);
