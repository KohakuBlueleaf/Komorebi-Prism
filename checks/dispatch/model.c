/* A model of the cores that ask the tile pull: each core holds at most `depth`
 * threads, runs them in order at costs drawn from their slice's weight, tells each one
 * ended (latest wins) and asks again; a core answered none asks no more. The same
 * choice on four host threads, each the X280 core of a quarter of the cores. Host
 * only. */
#include <pthread.h>
#include <stdlib.h>
#include <string.h>

#include "dispatch_choose.h"

#define NEVER 0xFFFFFFFFFFFFFFFFull
#define STEPS_MOST 50000000u
#define X280_CORES 4

static kmx_message g_tell[KMX_PORTS_CORES];
static uint32_t g_fresh[KMX_PORTS_CORES];
static uint64_t g_seed;

int kmx_port_told(int core, kmx_message* message) {
    if (!g_fresh[core]) {
        return KMX_NONE;
    }
    *message = g_tell[core];
    g_fresh[core] = 0;
    return KMX_OK;
}

static uint32_t random_below(uint32_t below) {
    g_seed = g_seed * 6364136223846793005ull + 1442695040888963407ull;
    return below ? (uint32_t)((g_seed >> 33) % below) : 0u;
}

uint32_t dpm_bytes(void) {
    return DP_CHOOSE_BYTES;
}

/* The state for a run: reset, then each slice's records and weight. */
static dp_choose_t* state_of(
    const uint32_t* setting, const uint32_t* records, const uint32_t* weights
) {
    dp_choose_t* state = (dp_choose_t*)calloc(1, sizeof(dp_choose_t));
    if (dp_choose_reset(
            state,
            setting[0],
            setting[1],
            setting[2],
            setting[3],
            setting[4],
            setting[5]
        )) {
        free(state);
        return 0;
    }
    for (uint32_t slice = 0; slice < setting[4]; slice++) {
        dp_choose_slice(state, slice, records[slice], weights[slice]);
    }
    return state;
}

/* An answer noted: the number's core in who[], a number out of range or handed twice
 * counted. stats: 0 twice, 4 handed, 6 out of range, 3 marked near. */
static void note(
    const dp_choose_t* state,
    uint32_t core,
    uint64_t answer,
    uint32_t* who,
    uint32_t* stats
) {
    const uint32_t number = (uint32_t)answer, word = (uint32_t)(answer >> 32);
    const uint32_t slice = TR_SLICE_OF(number), place = TR_PLACE_OF(number);
    if (slice >= state->slices || place >= state->slice[slice].records) {
        __atomic_fetch_add(&stats[6], 1u, __ATOMIC_RELAXED);
        return;
    }
    if (__atomic_exchange_n(&who[number], core, __ATOMIC_RELAXED) != KMX_PULL_NONE) {
        __atomic_fetch_add(&stats[0], 1u, __ATOMIC_RELAXED);
    }
    __atomic_fetch_add(&stats[4], 1u, __ATOMIC_RELAXED);
    if (TA_HINT(word) & TA_HINT_NEAR) {
        __atomic_fetch_add(&stats[3], 1u, __ATOMIC_RELAXED);
    }
}

/* A core of the model: the threads it holds (number, end) oldest first, its next ask,
 * whether it was answered none. */
typedef struct {
    uint32_t number[8];
    uint64_t end[8];
    uint32_t held, done, given;
    uint64_t ask;
} model_core_t;

/* setting: policy, near, first, count, slices, slices a row, depth (1 to 8).
 * Runs the pull; stats: 0 twice, 1 refused while a record was left, 2 a record of
 * another rank's slice (any policy), 3 near, 4 handed, 5 steps, 6 out of range, 7
 * the model's time at the end. */
uint32_t dpm_run(
    const uint32_t* setting,
    const uint32_t* records,
    const uint32_t* weights,
    uint32_t seed,
    uint32_t* who,
    uint32_t* stats
) {
    dp_choose_t* state = state_of(setting, records, weights);
    if (state == 0) {
        return 1u;
    }
    const uint32_t first = setting[2], count = setting[3], depth = setting[6];
    uint32_t total = 0;
    for (uint32_t slice = 0; slice < setting[4]; slice++) {
        total += records[slice];
    }
    g_seed = seed;
    memset(g_fresh, 0, sizeof g_fresh);
    model_core_t* core = (model_core_t*)calloc(count, sizeof(model_core_t));
    for (uint32_t c = 0; c < count; c++) {
        core[c].ask = random_below(16);
    }
    uint32_t steps = 0, live = count;
    uint64_t now = 0;
    while (live && steps++ < STEPS_MOST) {
        uint32_t next = 0, ending = 0;
        uint64_t best = NEVER;
        for (uint32_t c = 0; c < count; c++) {
            if (core[c].held && core[c].end[0] < best) {
                best = core[c].end[0], next = c, ending = 1;
            }
            if (!core[c].done && core[c].ask < best) {
                best = core[c].ask, next = c, ending = 0;
            }
        }
        model_core_t* one = &core[next];
        const uint32_t port = first + next;
        now = best;
        if (!ending) {
            const uint64_t answer = dp_choose((int)port, one->given, (uint64_t)state);
            const uint32_t number = (uint32_t)answer;
            if (number == KMX_PULL_NONE) {
                stats[1] += stats[4] < total;
                one->done = 1;
                one->ask = NEVER;
            } else {
                one->given++;
                note(state, port, answer, who, stats);
                const uint32_t slice = TR_SLICE_OF(number);
                stats[2] += slice < state->slices && slice % count != next;
                const uint32_t mean = records[slice % setting[4]]
                    ? weights[slice % setting[4]] / records[slice % setting[4]]
                    : 1u;
                const uint64_t last = one->held ? one->end[one->held - 1u] : now;
                one->number[one->held] = number;
                one->end[one->held] = (last > now ? last : now) + 20u + mean +
                    random_below(mean + 20u);
                one->held++;
                one->ask = one->held < depth ? now + random_below(8) : NEVER;
            }
        } else {
            g_tell[port].w[0] = one->number[0];
            g_tell[port].w[1] = (uint32_t)(now >> 10);
            g_tell[port].w[2] = 1u;
            g_fresh[port] = 1;
            for (uint32_t i = 1; i < one->held; i++) {
                one->number[i - 1u] = one->number[i];
                one->end[i - 1u] = one->end[i];
            }
            one->held--;
            if (!one->done && one->ask == NEVER) {
                one->ask = now + random_below(8);
            }
        }
        live = 0;
        for (uint32_t c = 0; c < count; c++) {
            live += !core[c].done || core[c].held;
        }
    }
    stats[5] = steps;
    stats[7] = (uint32_t)now;
    free(core);
    free(state);
    return 0;
}

/* The threaded run's shared words. */
typedef struct {
    dp_choose_t* state;
    uint32_t first, count;
    uint32_t* who;
    uint32_t* stats;
} threads_t;

typedef struct {
    threads_t* shared;
    uint32_t x280;
} part_t;

/* One X280 core: its cores (port % 4 its number) ask in turn until each is answered
 * none. */
static void* serve(void* arg) {
    const part_t* part = (const part_t*)arg;
    threads_t* shared = part->shared;
    uint8_t done[KMX_PORTS_CORES] = {0};
    uint32_t live = 0;
    for (uint32_t c = 0; c < shared->count; c++) {
        live += (shared->first + c) % X280_CORES == part->x280;
    }
    while (live) {
        for (uint32_t c = 0; c < shared->count; c++) {
            const uint32_t port = shared->first + c;
            if (port % X280_CORES != part->x280 || done[port]) {
                continue;
            }
            const uint64_t answer = dp_choose((int)port, 0, (uint64_t)shared->state);
            if ((uint32_t)answer == KMX_PULL_NONE) {
                done[port] = 1;
                live--;
                continue;
            }
            note(shared->state, port, answer, shared->who, shared->stats);
        }
    }
    return 0;
}

/* The same choice on four threads at once; stats as dpm_run's 0, 3, 4 and 6. */
uint32_t dpm_threads(
    const uint32_t* setting,
    const uint32_t* records,
    const uint32_t* weights,
    uint32_t* who,
    uint32_t* stats
) {
    threads_t shared = {
        state_of(setting, records, weights), setting[2], setting[3], who, stats
    };
    if (shared.state == 0) {
        return 1u;
    }
    memset(g_fresh, 0, sizeof g_fresh);
    pthread_t thread[X280_CORES];
    part_t part[X280_CORES];
    for (uint32_t h = 0; h < X280_CORES; h++) {
        part[h].shared = &shared;
        part[h].x280 = h;
        pthread_create(&thread[h], 0, serve, &part[h]);
    }
    for (uint32_t h = 0; h < X280_CORES; h++) {
        pthread_join(thread[h], 0);
    }
    free(shared.state);
    return 0;
}
