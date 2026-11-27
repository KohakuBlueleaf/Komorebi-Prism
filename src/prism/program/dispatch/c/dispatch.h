/* The frame's thread as Komorebi's pulls: a view is the count pull (logged), the sums
 * command, the place pull (the log replayed) and the tile pull (dp_choose). The
 * places, regions and builders are the generated pipeline.h's (DP_*). */
#pragma once

#include <stdint.h>

#include "director.h"
#include "dispatch_choose.h"
#include "thread/frame.h"

#ifndef DP_RANGES_MOST
#error "DP_RANGES_MOST: the count ranges a view holds at most, the capacity's"
#endif

#ifndef DP_SLICE_TILES
#error "DP_SLICE_TILES: the tiles a slice holds, the capacity's"
#endif

/* The view's codes: a region under its need; a number out of range (range
 * blocks, policy, a grid); more layers than a record holds; more ranges or slices than
 * the capacity; a slice with more records than TR_SLICE_RECORDS; fewer list slots than
 * a layer's entries; a command's block refused; a pull refused or its log full; each
 * pull late, by its place; the need page's copy refused or late */
#define DP_SMALL_REGION (DR_UNIT_CODES + 64u)
#define DP_BAD_NUMBERS (DR_UNIT_CODES + 66u)
#define DP_BAD_LAYERS (DR_UNIT_CODES + 67u)
#define DP_TOO_MANY (DR_UNIT_CODES + 68u)
#define DP_SLICE_FULL (DR_UNIT_CODES + 69u)
#define DP_LISTS_SMALL (DR_UNIT_CODES + 70u)
#define DP_BAD_BLOCK (DR_UNIT_CODES + 71u)
#define DP_PULL_BAD (DR_UNIT_CODES + 72u)
#define DP_LATE_COUNT (DR_UNIT_CODES + 73u)
#define DP_LATE_PLACE (DR_UNIT_CODES + 74u)
#define DP_LATE_TILE (DR_UNIT_CODES + 75u)
#define DP_NEED_LATE (DR_UNIT_CODES + 76u)

/* The need page (the number DP_N_NEED: a tensor of one page of DP_NEED_BYTES; 0: none),
 * copied from the region DP_REGION_NEED when a view stops with DP_LISTS_SMALL: the
 * view's index and kind, the code, then each layer's entries placed by its row index
 * (0 for a layer the view does not draw) */
#define DP_NEED_VIEW 0u
#define DP_NEED_KIND 1u
#define DP_NEED_CODE 2u
#define DP_NEED_ENTRIES 4u
#define DP_NEED_WORDS 16u
#define DP_NEED_BYTES 64u

/* A view's phases, the bits of the number DP_N_PHASES (0: every phase). Without the
 * sums, a phase after them takes the slices' words the host left in their region. */
#define DP_PHASE_COUNT 1u
#define DP_PHASE_SUMS 2u
#define DP_PHASE_PLACE 4u
#define DP_PHASE_TILE 8u
#define DP_PHASE_ALL 15u

/* The progress marks (kmx_progress) before each wait of a view */
#define DP_WHERE_COUNT 0xD1u
#define DP_WHERE_SUMS 0xD2u
#define DP_WHERE_PLACE 0xD3u
#define DP_WHERE_TILE 0xD4u

/* The tiles across and down of a grid word (grid.h: bits 4 to 17 and 18 to 31, 0
 * there 32) */
#define DP_GRID_ACROSS(word) (((word) >> 4 & 0x3FFFu) ? ((word) >> 4 & 0x3FFFu) : 32u)
#define DP_GRID_DOWN(word) (((word) >> 18) ? ((word) >> 18) : 32u)

/* Once: the regions checked against their need. 0, or DP_SMALL_REGION. */
uint32_t dp_setup(dr_frame_t* frame);

/* A view: the page, then its phases (DP_N_PHASES): the count pull, the sums, the
 * running sum over the slices, the place pull, the steps' frame words, the tile pull.
 * 0, or the first code. */
uint32_t dp_view(dr_frame_t* frame, const dr_view_t* view);

/* Generated (pipeline.c): each step's <step>_frame_words(frame, view, page) in the
 * steps' order (a DEPTH view: the steps with depth); the first code that is not 0. */
uint32_t dp_frame_words(dr_frame_t* frame, const dr_view_t* view, uint32_t* page);
