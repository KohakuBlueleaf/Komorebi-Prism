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

/* The handler's memory (the command space's part frame_memory): the movers' shared
 * line, then from the kept state's first byte the tile thread's part (the steps' kept
 * state, then the working planes) and each kind's kept state over the same bytes. In
 * the shared line: mover B's command, its threads ended, the time each ended (FM_RING a
 * ring by the thread's place); mover A's scratch for a record and its slice's words;
 * from FM_COMPUTE_AT each compute CPU's part (FM_COMPUTE_BYTES a CPU, unpack, math,
 * pack): its context, the descriptor it took, the descriptor's tile. */
#define FM_SHARED_BYTES 1216u
#define FM_COMPUTE_AT 256u
#define FM_COMPUTE_BYTES 320u
#define FM_B_SEQUENCE 0u
#define FM_B_DONE 1u
#define FM_B_ENDS 4u
#define FM_RING 4u
#define FM_RECORD_AT 64u
#define FM_SLICE_AT 128u
#define FM_ALIGN 64u

/* The account (built with PRISM_FRAME_ACCOUNT 1, else none): FX_L1_BYTES of the
 * handler's memory after the shared line, set at each command's start on mover A
 * before it hands anything on: the command's block (FX_BLOCK_WORDS), mover A's ask and
 * answer times by a thread's place (FX_TAKEN_AT, FM_RING), pack's step ends by a
 * thread's place (FX_STEPS_AT, FX_STEPS a thread), FM_RING records being written
 * (FX_STAGE_AT), the head (FX_HEAD_AT: the records written since the load). A core's
 * page of the account tensor (frame page TF_ACCOUNT): the head's FX_HEAD_WORDS, a block
 * a (view, pull) from FX_PAGE_BLOCKS (FX_VIEWS views, FX_ACCOUNT_PULLS pulls each), a
 * record a thread from FX_RECORDS_AT (TF_ACCOUNT_RECORDS a ring); written by mover A at
 * the command's end and a thread's end. Times in wall clock cycles. */
#define FX_L1_BYTES 1024u
#define FX_BLOCK_WORDS 64u
#define FX_TAKEN_AT 64u
#define FX_STEPS_AT 72u
#define FX_STEPS 8u
#define FX_STAGE_AT 104u
#define FX_HEAD_AT 168u
#define FX_HEAD_WORDS 16u
#define FX_DONE_AT 184u /* mover B's, then each compute CPU's: the command it ended */
#define FX_PAGE_BLOCKS 16u
#define FX_VIEWS 8u
#define FX_ACCOUNT_PULLS 3u
#define FX_RECORD_WORDS 16u
#define FX_RECORDS_AT 1600u
/* A block: a mover's words from FX_MOVER_A or FX_MOVER_B, then each compute CPU's
 * FX_CPU_WORDS from FX_CPU_AT (unpack, math, pack): its threads' cycles, a step's
 * cycles from FX_CPU_STEP (a kind: step 0), its threads. */
#define FX_MOVER_A 0u
#define FX_MOVER_B 16u
#define FX_THREADS 0u /* threads run (mover A: taken) */
#define FX_ASK 1u     /* A: asked and answered a thread; B: waiting for a descriptor */
#define FX_NONE 2u    /* A: asked and answered none left */
#define FX_AHEAD 3u   /* A: waiting for the thread before the one taken ahead */
#define FX_DRAIN 4u   /* waiting for the threads taken to end */
#define FX_SPAN 5u    /* the command, start to end */
#define FX_RUN 6u     /* running a thread's share (its movement) */
#define FX_SERVE 7u   /* serving asks and output blocks */
#define FX_BYTES_MESH 8u
#define FX_BYTES_SHADE 9u
#define FX_BYTES_LISTS 10u   /* lists read (tile pull), list slots written (place) */
#define FX_BYTES_RECORDS 11u /* records and slices' words read */
#define FX_BYTES_ASKED 12u   /* pages read for the compute side's asks */
#define FX_BYTES_OUT 13u     /* output blocks written */
#define FX_BYTES_PAGES 14u   /* counts, rows and positions pages read or written */
#define FX_BYTES_OTHER 15u   /* the camera */
#define FX_CPU_AT 32u
#define FX_CPU_WORDS 10u
#define FX_CPU_STEP 1u
#define FX_CPU_THREADS 9u
#define FX_PLACE_LOAD 62u /* the place pull's positions and slices read, cycles */
#define FX_PLACE_WAIT 63u /* the place pull's waits for the compute side's pages */
/* A record: view | kind << 8 | pull << 16, the number, the count, asked, answered,
 * started, ended on mover A, on mover B, the cost told, pack's step ends from word 9 */
#define FX_R_VIEW 0u
#define FX_R_NUMBER 1u
#define FX_R_COUNT 2u
#define FX_R_ASKED 3u
#define FX_R_TAKEN 4u
#define FX_R_START 5u
#define FX_R_END_A 6u
#define FX_R_END_B 7u
#define FX_R_COST 8u
#define FX_R_STEPS 9u

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
