/* The job thread's runtime (jobs.h): the region table at the start, the peers brought
 * to serve, the parts over every core of the image, the drops, the copies. */
#include "jobs.h"

_Static_assert(
    JB_BLOCK_BYTES <= JB_REGION_JOBS_BLOCK_BYTES, "the job's block in its region"
);
_Static_assert(
    JB_DROP_AT + sizeof(jb_drop_t) <= JB_CALL_AT, "a drop's ranges before the call"
);

/* The runtime's state, this cluster's (in .data: the image links no .bss). */
static jb_state_t g_state
    __attribute__((section(".data"))) = {{0}, {0}, {0}, 1u, 0, 0, 0};

/* The part a jb_parallel call runs (read on every cluster from the block). */
typedef struct {
    uint64_t part;
    uint64_t drop; /* 1: the call is a drop, its ranges in the input */
} call_t;

jb_state_t* jb_state(void) {
    return &g_state;
}

void* jb_region(uint32_t id, uint64_t at) {
    return (uint8_t*)g_state.regions[id] + at;
}

uint64_t jb_region_bytes(uint32_t id) {
    return g_state.bytes[id];
}

uint32_t jb_region_address(uint32_t id) {
    return g_state.address[id];
}

void jb_flush(uint32_t id, uint64_t at, uint64_t bytes) {
    if (bytes) {
        kmx_flush_at((int)id, at, bytes);
    }
}

void jb_invalidate(uint32_t id, uint64_t at, uint64_t bytes) {
    if (bytes) {
        kmx_invalidate_at((int)id, at, bytes);
    }
}

void* jb_input(void) {
    return jb_region(JB_REGION_JOBS_BLOCK, 0);
}

uint32_t* jb_given(uint32_t index) {
    return (uint32_t*)jb_region(JB_REGION_JOBS_BLOCK, JB_BLOCK_IN + JB_LINE * index);
}

/* Where the call's words lie: the last line the lead writes. */
static call_t* call_words(void) {
    return (call_t*)jb_region(JB_REGION_JOBS_BLOCK, JB_CALL_AT);
}

uint32_t jb_parts(void) {
    return g_state.parts;
}

/* Cluster `cluster`'s place among the image's clusters (the lead's 0). */
static uint32_t cluster_place(int cluster) {
    const uint32_t mask = kmx_clusters();
    uint32_t place = 0;
    for (int below = 1; below < cluster; below++) {
        place += (mask >> below) & 1u;
    }
    return place;
}

void jb_share(
    uint32_t index,
    uint32_t of,
    uint64_t count,
    uint64_t grain,
    uint64_t* first,
    uint64_t* end
) {
    const uint64_t grains = (count + grain - 1) / grain;
    *first = grain * (grains * index / of);
    *end = grain * (grains * (index + 1) / of);
    *first = *first < count ? *first : count;
    *end = *end < count ? *end : count;
}

/* A drop's ranges on this cluster, range by range over its four cores. */
static void drop_part(int core, const jb_drop_t* drop) {
    for (uint32_t i = 0; i < drop->count && i < JB_DROP_RANGES; i++) {
        uint64_t first, end;
        jb_share((uint32_t)core, JB_CORES, drop->bytes[i], JB_LINE, &first, &end);
        jb_invalidate(drop->region[i], drop->at[i] + first, end - first);
    }
}

/* What every core of every cluster runs for one jb_parallel call. */
static void each_core(int cluster, int core, uint64_t arg) {
    (void)arg;
    if (cluster != kmx_lead()) {
        jb_invalidate(JB_REGION_JOBS_BLOCK, 0, JB_BLOCK_IN);
    }
    const call_t* call = call_words();
    if (call->drop) {
        drop_part(core, (const jb_drop_t*)jb_region(JB_REGION_JOBS_BLOCK, JB_DROP_AT));
        return;
    }
    const uint32_t index = JB_CORES * cluster_place(cluster) + (uint32_t)core;
    ((jb_part_t)(uintptr_t)call->part)(index, g_state.parts);
}

/* One kmx_parallel_all call of `call`: 0, or JB_PARALLEL. */
static uint32_t run_call(uint64_t part, uint64_t drop) {
    call_t* call = call_words();
    call->part = part;
    call->drop = drop;
    jb_flush(JB_REGION_JOBS_BLOCK, 0, JB_BLOCK_IN);
    if (kmx_parallel_all(each_core, 0) != KMX_OK) {
        return JB_PARALLEL;
    }
    jb_invalidate(JB_REGION_JOBS_BLOCK, JB_BLOCK_IN, JB_PARTS_MOST * JB_LINE);
    return 0;
}

uint32_t jb_parallel(jb_part_t part) {
    return run_call((uint64_t)(uintptr_t)part, 0);
}

void jb_drop_start(jb_drop_t* drop) {
    drop->count = 0;
}

void jb_drop_add(jb_drop_t* drop, uint32_t region, uint64_t at, uint64_t bytes) {
    if (drop->count < JB_DROP_RANGES && bytes) {
        drop->region[drop->count] = region;
        drop->at[drop->count] = at;
        drop->bytes[drop->count++] = bytes;
    }
}

uint32_t jb_drop_run(jb_drop_t* drop) {
    jb_drop_t* input = (jb_drop_t*)jb_region(JB_REGION_JOBS_BLOCK, JB_DROP_AT);
    input->count = drop->count;
    for (uint32_t i = 0; i < drop->count && i < JB_DROP_RANGES; i++) {
        input->region[i] = drop->region[i];
        input->at[i] = drop->at[i];
        input->bytes[i] = drop->bytes[i];
    }
    return run_call(0, 1);
}

uint32_t jb_fetch(
    uint32_t id,
    uint64_t at,
    const kmx_dram* from,
    uint64_t bytes,
    uint32_t first,
    uint32_t count
) {
    kmx_event event;
    const int status = kmx_fetch(
        (int)id, at, from, bytes, first, count, kmx_time() + JB_WAIT_TICKS, &event
    );
    return status == KMX_OK && event.kind == KM_EVENT_DONE ? 0u : JB_RING;
}

uint32_t jb_store(
    uint32_t id,
    uint64_t at,
    const kmx_dram* to,
    uint64_t bytes,
    uint32_t first,
    uint32_t count
) {
    kmx_event event;
    const int status = kmx_store(
        (int)id, at, to, bytes, first, count, kmx_time() + JB_WAIT_TICKS, &event
    );
    return status == KMX_OK && event.kind == KM_EVENT_DONE ? 0u : JB_RING;
}

uint32_t jb_ticks(uint64_t* mark) {
    const uint64_t now = kmx_time();
    const uint32_t ticks = (uint32_t)(now - *mark);
    *mark = now;
    return ticks;
}

uint32_t jb_ready(void) {
    if (g_state.set_up) {
        return g_state.set_up;
    }
    if (!g_state.lead) {
        return JB_NOT_LEAD;
    }
    return g_state.peers;
}

uint32_t jb_serve(const km_command_t* command) {
    (void)command;
    if (g_state.lead) {
        return JB_NOT_LEAD;
    }
    return kmx_serve() == KMX_OK ? 0u : JB_PARALLEL;
}

/* An empty part: the first kmx_parallel_all call, which waits for the peers. */
static void nothing(int cluster, int core, uint64_t arg) {
    (void)cluster;
    (void)core;
    (void)arg;
}

/* The lead: the command JOBS_SERVE sent to every other cluster of the image (not
 * waited for: it is answered when the run stops), then one empty call, which waits
 * for them to serve within the thread's deadline. 0, or JB_PEERS. */
static uint32_t peers_serve(void) {
    const uint32_t mask = kmx_clusters();
    for (int cluster = 1; cluster < 4; cluster++) {
        if (cluster == kmx_cluster() || !((mask >> cluster) & 1u)) {
            continue;
        }
        km_command_t command;
        kmx_command(
            &command,
            0,
            JB_HANDLER_JOBS_SERVE,
            KM_GROUP_CLUSTER_BASE + (uint32_t)cluster,
            1
        );
        uint32_t handle;
        const uint64_t until = kmx_time() + JB_PEERS_TICKS;
        int status = kmx_submit(&command, &handle);
        while (status == KMX_FULL && kmx_time() < until) {
            status = kmx_submit(&command, &handle);
        }
        if (status != KMX_OK) {
            return JB_PEERS;
        }
    }
    return kmx_parallel_all(nothing, 0) == KMX_OK ? 0u : JB_PEERS;
}

int kmx_main(int core) {
    (void)core;
    const kmx_args* arguments = kmx_args_get();
    jb_state_t* state = &g_state;
    state->set_up = arguments->nregions == JB_REGIONS ? 0u : JB_BAD_ARGS;
    for (uint32_t id = 0; id < JB_REGIONS && state->set_up == 0; id++) {
        state->regions[id] = kmx_region((int)id, &state->bytes[id]);
        if (state->regions[id] == 0 || arguments->region[id].offset >> 32) {
            state->set_up = JB_BAD_ARGS;
        }
        state->address[id] = (uint32_t)arguments->region[id].offset;
    }
    uint32_t clusters = 0;
    for (int cluster = 1; cluster < 4; cluster++) {
        clusters += (kmx_clusters() >> cluster) & 1u;
    }
    state->parts = JB_CORES * (clusters ? clusters : 1u);
    state->lead = kmx_lead() == kmx_cluster();
    if (state->parts > JB_PARTS_MOST) {
        state->set_up = JB_BAD_ARGS;
    }
    state->peers = state->set_up == 0 && state->lead ? peers_serve() : 0u;
    return (int)(state->set_up ? state->set_up : state->peers);
}
