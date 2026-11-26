/* The host check's stand-in for Komorebi's kmx.h: the port's tell, the ports' cores
 * and the pull's word, as the tile pull's choice uses them. */
#pragma once

#include <stdint.h>

#define KMX_OK 0
#define KMX_NONE 4
#define KMX_PORTS_CORES 128u
#define KMX_PULL_NONE 0xFFFFFFFFu
#define KMX_PULL_WORD(range, word) \
    ((uint64_t)(uint32_t)(range) | (uint64_t)(uint32_t)(word) << 32)

typedef struct {
    uint32_t sequence, w[3];
} kmx_message;

/* The model's: `core`'s newest tell if not looked at yet. */
int kmx_port_told(int core, kmx_message* message);
