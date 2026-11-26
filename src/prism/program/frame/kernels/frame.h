/* The handler `work`'s layouts: what mover A hands the compute CPUs and mover B, the
 * request rings' pages, an output block's header, the movers' shared line and the
 * places of the loop's waits. Shared by the loop's kernels, the steps and kinds that
 * run in it, and prism.program.frame (which reads the defines). */
#pragma once

#include <stdint.h>

#include "../../../core/include/thread/answer.h"
#include "../../../core/include/thread/frame.h"
#include "../../../core/include/thread/record.h"

/* A thread's descriptor, FD_WORDS words: pushed by mover A to the compute CPUs and to
 * mover B. FD_KIND FD_END: the command's end (no thread). */
#define FD_WORDS 32u
#define FD_PAGES 2u       /* a descriptor ring's pages: the running and one ahead */
#define FD_KIND 0u        /* the pull's kind (answer.h TP_*), FD_END: the end */
#define FD_NUMBER 1u      /* the pull's number (a range's first, a record's number) */
#define FD_COUNT 2u       /* the pull's count */
#define FD_WORD 3u        /* the tile pull's word (answer.h TA_WORD) */
#define FD_SEQUENCE 4u    /* the thread's place among the command's, from 0 */
#define FD_LAYER 5u       /* a range: its layer */
#define FD_FIRST_BLOCK 6u /* a range: its first triangle block in the layer */
#define FD_BLOCKS 7u      /* a range: its blocks */
#define FD_RECORD 8u      /* a tile: its record (record.h), slots made absolute */
#define FD_END 0u

/* A request ring's page (the compute side's ask of one mover): FA_COUNT the pages
 * asked, each read from the tensor at bank address FA_BASE in pages of FA_PAGE_BYTES
 * into L1; an entry is (page, L1 address) from FA_ENTRY_AT. FA_COUNT FA_THREAD_END:
 * the running thread ended, FA_OUTPUTS output blocks pushed into this mover's halves.
 */
#define FA_BYTES 512u
#define FA_PAGES 2u
#define FA_COUNT 0u
#define FA_BASE 1u
#define FA_PAGE_BYTES 2u
#define FA_OUTPUTS 3u
#define FA_ENTRY_AT 4u
#define FA_ENTRY_WORDS 2u
#define FA_THREAD_END 0xFFFFFFFFu
#define FA_ENTRIES ((FA_BYTES / 4u - FA_ENTRY_AT) / FA_ENTRY_WORDS)
/* A done ring's page: no content, one an ask served. */
#define FN_BYTES 64u
#define FN_PAGES 2u

/* An output block: a header of FO_HEADER_BYTES, then the payload. The mover that
 * takes it converts the payload and writes it to the frame page's TF_TARGET, page
 * FO_PAGE in pages of FO_PAGE_BYTES, from byte FO_OFFSET. */
#define FO_HEADER_BYTES 16u
#define FO_PAGE 0u
#define FO_OFFSET 1u
#define FO_BYTES 2u
#define FO_PAGE_BYTES 3u

/* The list stream: blocks dealt to the movers by the pattern AB; a mover issues
 * FL_CHUNK_BLOCKS blocks at a time (a multiple of the pattern's length), each half
 * holds FL_HALF_BLOCKS blocks. */
#define FL_CHUNK_BLOCKS 2u
#define FL_HALF_BLOCKS 2u

/* The handler's memory (the field frame_memory): the movers' shared line, then the
 * kept state, then the working planes. In the shared line: mover B's command, its
 * threads ended, the time each ended (FM_RING a ring by the thread's place); mover A's
 * scratch for a record and its slice's words. */
#define FM_SHARED_BYTES 256u
#define FM_B_SEQUENCE 0u
#define FM_B_DONE 1u
#define FM_B_ENDS 4u
#define FM_RING 4u
#define FM_RECORD_AT 64u
#define FM_SLICE_AT 128u
#define FM_ALIGN 64u

/* The places of the loop's waits and give-ups (the gave-up word's where). */
#define FW_PAGE 112u            /* mover A: room for the frame's page */
#define FW_DESCRIPTOR_ROOM 113u /* mover A: room in a descriptor ring */
#define FW_DESCRIPTOR 114u      /* mover B: its next descriptor */
#define FW_AHEAD 115u           /* mover A: the thread before the one taken ahead */
#define FW_LIST_ROOM 116u       /* a mover: room in its list half */
#define FW_REQUEST 117u         /* a mover: a request's reads landed */
#define FW_OUTPUT 118u          /* a mover: an output block's writes left */
#define FW_DRAIN 119u           /* a mover: the threads it took ended */
#define FW_RECORD 120u          /* mover A: a record and its slice's words landed */
#define FW_C_PAGE 121u          /* unpack: the frame's page */
#define FW_C_DESCRIPTOR 122u    /* unpack: a descriptor */
#define FW_C_MAIL 123u          /* a compute CPU: a word of another */
#define FW_C_ASK 124u           /* pack: room in a request ring */
#define FW_C_DONE 125u          /* pack: an ask served */
#define FW_C_OUT 126u           /* pack: room in an output half */
#define FW_BAD 127u             /* a bad block, descriptor, request or pull */
/* Compute's waits give up after FW_WAIT_CYCLES cycles. */
#define FW_WAIT_CYCLES 0x40000000u
