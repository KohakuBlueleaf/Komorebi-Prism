/* The post.show unit: SHOW, then the PUSH, each a command the cores run. */
#include "post_show_unit.h"

#if defined(POST_SHOW_TRANSMIT)
#include "thread/transmit.h"
#endif

_Static_assert(KM_TRANSFER_NONCE == SHOW_PUSH_NONCE, "a transfer's nonce is its a7");

/* The directory of the view's first layer's frame (every layer's colour, or the
 * nearest 1/z, is in it). */
static uint32_t first_directory(const dr_view_t* view) {
    const volatile uint32_t* layer = (const volatile uint32_t*)dr_region(
        DR_REGION_LAYERS, 4u * DR_LAYER_WORDS * view->index * DR_LAYERS
    );
    return layer[DR_POST_SHOW_TAKES_FRAME_VISIBILITY_DIRECTORY];
}

#if !defined(POST_SHOW_BY_LIGHT)
/* SHOW of the view's first layer: its directory, the display and its pages. */
static uint32_t show(dr_frame_t* frame, const dr_view_t* view) {
    const uint32_t directory = first_directory(view);
    km_command_t command;
    DR_POST_SHOW_BUILD(show)(&command, 0, 0, frame->workers, view->tiles);
    dr_word(&command, DR_PLACE(SHOW_DIRECTORY), directory);
    dr_word(
        &command, DR_PLACE(SHOW_DISPLAY), dr_number(frame, DR_POST_SHOW_N_SHOW_DISPLAY)
    );
    dr_word(
        &command, DR_PLACE(SHOW_PROFILE), dr_number(frame, DR_POST_SHOW_N_SHOW_PROFILE)
    );
    return dr_run(&command);
}
#endif

/* The PUSH from the words the host wrote into the push region, its nonce word XORed
 * with the frame's key. */
static uint32_t push(void) {
    const uint32_t at = DR_POST_SHOW_REGION_SHOW_PUSH_AT;
    dr_invalidate(DR_POST_SHOW_REGION_SHOW_PUSH, at, SHOW_PUSH_BYTES);
    const volatile uint32_t* words = (const volatile uint32_t*)DR_REGION(
        DR_POST_SHOW_REGION_SHOW_PUSH
    );
    const uint32_t header = words[SHOW_PUSH_HEADER], group = words[SHOW_PUSH_GROUP];
    km_command_t command;
    kmx_command(&command, header >> 24, header & 0xFFu, group & 0xFFFFu, group >> 16);
    command.hdr |= header & 0xFF00u;
    for (uint32_t word = 0; word < 10; word++) {
        dr_word(&command, word, words[SHOW_PUSH_ARGS + word]);
    }
    dr_word(
        &command,
        SHOW_PUSH_NONCE,
        words[SHOW_PUSH_ARGS + SHOW_PUSH_NONCE] ^ words[SHOW_PUSH_KEY]
    );
    return dr_run(&command);
}

/* COPY of a DEPTH view's first layer's 1/z plane into the view's target. */
static uint32_t copy(dr_frame_t* frame, const dr_view_t* view) {
    km_command_t command;
    DR_POST_SHOW_BUILD(copy)(
        &command,
        0,
        0,
        frame->workers,
        view->target_first,
        view->target_across,
        view->target_pages,
        view->grid
    );
    dr_word(&command, DR_PLACE(COPY_DIRECTORY), first_directory(view));
    dr_word(&command, DR_PLACE(COPY_TARGET), view->target);
    return dr_run(&command);
}

#if defined(POST_SHOW_TRANSMIT)
/* The directory of the view's last layer a DEPTH view draws (its glass layer when the
 * view keeps T), 0 when that is its first. */
static uint32_t glass_directory(const dr_frame_t* frame, const dr_view_t* view) {
    for (uint32_t layer = frame->layers; layer-- > 1u;) {
        const volatile uint32_t* row = (const volatile uint32_t*)dr_region(
            DR_REGION_LAYERS, 4u * DR_LAYER_WORDS * (view->index * DR_LAYERS + layer)
        );
        if (row[DR_L_DEPTH]) {
            return row[DR_POST_SHOW_TAKES_FRAME_VISIBILITY_DIRECTORY];
        }
    }
    return 0;
}

/* COPY_TRANSMIT of `directory`'s items, their planes from the first layer's frame:
 * with `codes` 0 T 1 over each band, else the bands' T codes. */
static uint32_t copy_transmit(
    dr_frame_t* frame, const dr_view_t* view, uint32_t directory, uint32_t codes
) {
    km_command_t command;
    DR_POST_SHOW_BUILD(copy_transmit)(
        &command,
        0,
        0,
        frame->workers,
        view->target_first,
        view->target_across,
        view->target_pages,
        view->grid,
        view->transmit,
        view->transmit_base,
        view->transmit_channels | (codes ? TRANSMIT_CODES : 0u)
    );
    dr_word(&command, DR_PLACE(COPY_TRANSMIT_DIRECTORY), directory);
    dr_word(&command, DR_PLACE(COPY_TRANSMIT_FRAME_DIRECTORY), first_directory(view));
    dr_word(&command, DR_PLACE(COPY_TRANSMIT_TARGET), view->target);
    return dr_run(&command);
}

/* COPY, then for a view keeping T: T 1 over every tile, then its glass layer's items'
 * codes (the glass SHADE's, in the first layer's frame). */
static uint32_t copy_kept(dr_frame_t* frame, const dr_view_t* view) {
    uint32_t code = copy(frame, view);
    if (code != 0 || view->transmit == 0) {
        return code;
    }
    code = copy_transmit(frame, view, first_directory(view), 0u);
    const uint32_t glass = glass_directory(frame, view);
    return code != 0 || glass == 0 ? code : copy_transmit(frame, view, glass, 1u);
}
#endif

uint32_t post_show_unit_frame(dr_frame_t* frame, const dr_view_t* view) {
    if (view->kind == DR_VIEW_DEPTH) {
#if defined(POST_SHOW_TRANSMIT)
        return copy_kept(frame, view);
#else
        return copy(frame, view);
#endif
    }
    uint64_t mark = kmx_time();
#if defined(POST_SHOW_BY_LIGHT)
    uint32_t code = 0; /* LIGHT's last command wrote the display */
    frame->times[DR_POST_SHOW_T_SHOW] = 0;
#else
    uint32_t code = show(frame, view);
    frame->times[DR_POST_SHOW_T_SHOW] = dr_ticks(&mark);
#endif
    if (code == 0 && dr_number(frame, DR_POST_SHOW_N_SHOW_PUSHES)) {
        code = push();
        frame->times[DR_POST_SHOW_T_PUSH] = dr_ticks(&mark);
    }
    return code;
}
