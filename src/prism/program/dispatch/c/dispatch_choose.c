/* The tile pull's choice (dispatch_choose.h): preference, order, kept. */
#include "dispatch_choose.h"

_Static_assert(sizeof(dp_slice_t) == 4u * DP_SLICE_WORDS, "dp_slice_t words");
_Static_assert(sizeof(dp_core_t) == 4u * DP_CORE_WORDS, "dp_core_t words");
_Static_assert(sizeof(dp_choose_t) == DP_CHOOSE_BYTES, "dp_choose_t words");

static uint32_t load(const uint32_t* word) {
    return __atomic_load_n(word, __ATOMIC_RELAXED);
}

uint32_t dp_choose_reset(
    dp_choose_t* state,
    uint32_t policy,
    uint32_t near,
    uint32_t first,
    uint32_t count,
    uint32_t slices,
    uint32_t across,
    uint32_t slice_tiles
) {
    if (policy >= DP_POLICIES || count == 0 || first + count > KMX_PORTS_CORES ||
        slices > DP_SLICES_MOST || across == 0 || slice_tiles == 0) {
        return 1u;
    }
    state->policy = policy;
    state->near = near;
    state->slices = slices;
    state->first = first;
    state->count = count;
    state->cursor = 0;
    state->near_given = 0;
    for (uint32_t core = 0; core < KMX_PORTS_CORES; core++) {
        state->core[core].last = DP_NO_SLICE;
        state->core[core].codes = state->core[core].cost = 0;
        state->core[core].tells = 0;
    }
    for (uint32_t slice = 0; slice < slices; slice++) {
        const uint32_t tile = slice * slice_tiles;
        dp_slice_t* one = &state->slice[slice];
        one->records = one->next = one->weight = 0;
        one->row = tile / across;
        one->column = tile % across / slice_tiles;
    }
    return 0;
}

void dp_choose_slice(
    dp_choose_t* state, uint32_t slice, uint32_t records, uint32_t weight
) {
    if (slice < state->slices) {
        state->slice[slice].records = records;
        state->slice[slice].weight = weight;
    }
}

/* Slices apart in the slice grid: the larger of the rows' and the columns' distance. */
static uint32_t distance(const dp_slice_t* a, const dp_slice_t* b) {
    const uint32_t rows = a->row > b->row ? a->row - b->row : b->row - a->row;
    const uint32_t columns = a->column > b->column ? a->column - b->column
                                                   : b->column - a->column;
    return rows > columns ? rows : columns;
}

/* The slice's weight not yet handed, estimated from its records handed; 0 when every
 * record is handed. */
static uint32_t weight_left(const dp_slice_t* slice) {
    const uint32_t next = load(&slice->next);
    if (next >= slice->records) {
        return 0;
    }
    return slice->weight - (uint32_t)((uint64_t)slice->weight * next / slice->records);
}

/* A place taken in `slice`: the place, or KMX_PULL_NONE when it was handed out. */
static uint32_t take(dp_slice_t* slice) {
    if (load(&slice->next) >= slice->records) {
        return KMX_PULL_NONE;
    }
    const uint32_t place = __atomic_fetch_add(&slice->next, 1u, __ATOMIC_RELAXED);
    return place < slice->records ? place : KMX_PULL_NONE;
}

/* Preference: the nearest slice with records left within `near` of the core's last
 * (ties: the heavier weight left), else the slice with the most weight left. */
static uint32_t prefer(dp_choose_t* state, uint32_t last, uint32_t* place) {
    for (uint32_t attempt = 0; attempt <= state->slices; attempt++) {
        uint32_t best = DP_NO_SLICE, best_distance = 0, best_left = 0;
        uint32_t heavy = DP_NO_SLICE, heavy_left = 0;
        for (uint32_t slice = 0; slice < state->slices; slice++) {
            const dp_slice_t* one = &state->slice[slice];
            if (load(&one->next) >= one->records) {
                continue;
            }
            const uint32_t left = weight_left(one);
            if (heavy == DP_NO_SLICE || left > heavy_left) {
                heavy = slice;
                heavy_left = left;
            }
            if (last == DP_NO_SLICE) {
                continue;
            }
            const uint32_t apart = distance(one, &state->slice[last]);
            if (apart <= state->near &&
                (best == DP_NO_SLICE || apart < best_distance ||
                 (apart == best_distance && left > best_left))) {
                best = slice;
                best_distance = apart;
                best_left = left;
            }
        }
        const uint32_t slice = best != DP_NO_SLICE ? best : heavy;
        if (slice == DP_NO_SLICE) {
            return DP_NO_SLICE;
        }
        *place = take(&state->slice[slice]);
        if (*place != KMX_PULL_NONE) {
            return slice;
        }
    }
    return DP_NO_SLICE;
}

/* Order: the first slice with records left, from the cursor on. */
static uint32_t in_order(dp_choose_t* state, uint32_t* place) {
    for (uint32_t slice = load(&state->cursor); slice < state->slices; slice++) {
        *place = take(&state->slice[slice]);
        if (*place != KMX_PULL_NONE) {
            return slice;
        }
        uint32_t expected = slice;
        __atomic_compare_exchange_n(
            &state->cursor, &expected, slice + 1u, 0, __ATOMIC_RELAXED, __ATOMIC_RELAXED
        );
    }
    return DP_NO_SLICE;
}

/* Kept: the core's own slices (s mod the group's cores is its rank), from its last. */
static uint32_t kept(
    dp_choose_t* state, uint32_t core, uint32_t last, uint32_t* place
) {
    if (core < state->first || core - state->first >= state->count) {
        return DP_NO_SLICE;
    }
    const uint32_t rank = core - state->first;
    for (
        uint32_t slice = last == DP_NO_SLICE ? rank : last; slice < state->slices;
        slice += state->count
    ) {
        *place = take(&state->slice[slice]);
        if (*place != KMX_PULL_NONE) {
            return slice;
        }
    }
    return DP_NO_SLICE;
}

uint64_t dp_choose(int core, uint32_t index, uint64_t arg) {
    (void)index;
    dp_choose_t* state = (dp_choose_t*)(uintptr_t)arg;
    if (core < 0 || (uint32_t)core >= KMX_PORTS_CORES) {
        return KMX_PULL_WORD(KMX_PULL_NONE, 0);
    }
    dp_core_t* asker = &state->core[core];
    kmx_message told;
    if (kmx_port_told(core, &told) == KMX_OK) {
        asker->cost = told.w[1];
        asker->codes = told.w[2];
        asker->tells++;
    }
    const uint32_t last = asker->last;
    uint32_t place = KMX_PULL_NONE, slice = DP_NO_SLICE;
    switch (state->policy) {
        case DP_POLICY_PREFER:
            slice = prefer(state, last, &place);
            break;
        case DP_POLICY_ORDER:
            slice = in_order(state, &place);
            break;
        default:
            slice = kept(state, (uint32_t)core, last, &place);
            break;
    }
    if (slice == DP_NO_SLICE) {
        return KMX_PULL_WORD(KMX_PULL_NONE, 0);
    }
    const uint32_t near = last != DP_NO_SLICE &&
        distance(&state->slice[slice], &state->slice[last]) <= state->near;
    if (near) {
        __atomic_fetch_add(&state->near_given, 1u, __ATOMIC_RELAXED);
    }
    asker->last = slice;
    return KMX_PULL_WORD(
        TR_NUMBER(slice, place), TA_WORD(0u, near ? TA_HINT_NEAR : 0u)
    );
}
