/* The camera area of a (view, layer): its view's page, and each core's page with its
 * blocks for COUNT and SETUP and the costs COUNT left (kernels/setup.h kArea*). */
#include "raster_unit.h"

/* A core's page of the area from page `area`, as words. */
static volatile uint32_t* core_page(uint32_t area, uint32_t core) {
    const uint32_t at = (area + 1 + core) * RASTER_K_AREA_PAGE_BYTES;
    return (volatile uint32_t*)DR_REGION(DR_RASTER_REGION_CAMERA) + at / 4;
}

void raster_view_page(const dr_view_t* view, uint32_t area) {
    const uint32_t at = area * RASTER_K_AREA_PAGE_BYTES;
    volatile uint32_t* page = (volatile uint32_t*)DR_REGION(DR_RASTER_REGION_CAMERA) +
        at / 4;
    for (uint32_t i = 0; i < RASTER_K_CAM_WORDS; i++) {
        page[i] = view->camera[i];
    }
    page[RASTER_K_VIEW_AT / 4 + RASTER_K_VIEW_GRID] = view->grid;
    page[RASTER_K_VIEW_AT / 4 + RASTER_K_VIEW_DEPTH] = view->kind == DR_VIEW_DEPTH;
    dr_flush(
        DR_RASTER_REGION_CAMERA, DR_RASTER_REGION_CAMERA_AT + at, 4 * RASTER_K_CAM_WORDS
    );
    dr_flush(
        DR_RASTER_REGION_CAMERA,
        DR_RASTER_REGION_CAMERA_AT + at + RASTER_K_VIEW_AT,
        4 * (RASTER_K_VIEW_DEPTH + 1)
    );
}

/* Bytes `at` to `at + bytes` of each core's page of the area swept: the cores in
 * DR_SWEEP_PARTS parts, a part a run of consecutive cores' pages (a strided span a page
 * apart). 0, or DR_PARALLEL. */
static uint32_t sweep_pages(
    uint32_t cores, uint32_t area, uint32_t at, uint32_t bytes
) {
    dr_sweep_t sweep;
    dr_sweep_start(&sweep, DR_RASTER_REGION_CAMERA);
    for (uint32_t part = 0; part < DR_SWEEP_PARTS; part++) {
        const uint32_t first = part * cores / DR_SWEEP_PARTS;
        const uint32_t end = (part + 1) * cores / DR_SWEEP_PARTS;
        dr_sweep_strided(
            &sweep,
            DR_RASTER_REGION_CAMERA_AT + (area + 1 + first) * RASTER_K_AREA_PAGE_BYTES +
                at,
            bytes,
            RASTER_K_AREA_PAGE_BYTES,
            end - first
        );
    }
    return dr_sweep_run(&sweep) ? DR_PARALLEL : 0u;
}

/* The costs COUNT left for the last ranges, read again from memory, into `total`: their
 * total, or 0 when a core's page holds another range's (not the last frame's ranges).
 * 0, or DR_PARALLEL. */
static uint32_t costs_total(
    uint32_t cores, const uint32_t* ranges, uint32_t area, uint64_t* total
) {
    *total = 0;
    if (sweep_pages(
            cores, area, RASTER_K_AREA_COSTS_AT, 4 * (RASTER_K_COST_KNOTS + 1)
        )) {
        return DR_PARALLEL;
    }
    uint64_t sum = 0;
    for (uint32_t core = 0; core < cores; core++) {
        const volatile uint32_t* costs = core_page(area, core) +
            RASTER_K_AREA_COSTS_AT / 4;
        if (costs[0] != ranges[core + 1] - ranges[core]) {
            return 0;
        }
        sum += costs[RASTER_K_COST_KNOTS];
    }
    *total = sum;
    return 0;
}

/* The cuts at equal parts of `total` over the last ranges' knots. */
static void cost_cuts(
    uint32_t cores,
    uint32_t blocks,
    const uint32_t* ranges,
    uint32_t area,
    uint64_t total,
    uint32_t* cut_blocks
) {
    uint32_t cut_index = 1;
    uint64_t want = total / cores; /* the cost before cut `cut_index` */
    uint64_t base = 0;             /* the cost of the cores before `core` */
    cut_blocks[0] = 0;
    for (uint32_t core = 0; core < cores && cut_index < cores; core++) {
        const volatile uint32_t* knots = core_page(area, core) +
            RASTER_K_AREA_COSTS_AT / 4;
        const uint64_t core_end = base + knots[RASTER_K_COST_KNOTS];
        const uint32_t first = ranges[core];
        const uint32_t count = ranges[core + 1] - first;
        while (cut_index < cores && want <= core_end) {
            uint32_t low = 1, high = RASTER_K_COST_KNOTS; /* the first knot >= want */
            while (low < high) {
                const uint32_t middle = (low + high) / 2;
                if (base + knots[middle] >= want) {
                    high = middle;
                } else {
                    low = middle + 1;
                }
            }
            const uint64_t cost = base + knots[low];
            const uint64_t last_cost = base + (low > 1 ? knots[low - 1] : 0);
            const uint32_t place = first + low * count / RASTER_K_COST_KNOTS;
            uint32_t block = first + (low - 1) * count / RASTER_K_COST_KNOTS;
            if (want > last_cost) {
                block += (uint32_t)((want - last_cost) * (place - block) /
                                    (cost - last_cost));
            }
            cut_blocks[cut_index] = block > cut_blocks[cut_index - 1]
                ? block
                : cut_blocks[cut_index - 1];
            cut_index++;
            want = total * cut_index / cores;
        }
        base = core_end;
    }
    for (; cut_index < cores; cut_index++) {
        cut_blocks[cut_index] = blocks;
    }
    cut_blocks[cores] = blocks;
}

uint32_t raster_ranges(
    const dr_frame_t* frame,
    raster_work_t* work,
    const dr_layer_t* layer,
    uint32_t area_index,
    uint32_t area
) {
    const uint32_t cores = frame->cores;
    const uint32_t blocks = layer->words[DR_RASTER_L_BLOCKS];
    uint32_t* ranges = work->ranges[area_index];
    uint64_t total = 0;
    if (work->ranged[area_index] && dr_number(frame, DR_RASTER_N_BALANCE) &&
        costs_total(cores, ranges, area, &total)) {
        return DR_PARALLEL;
    }
    if (total == 0) {
        for (uint32_t core = 0; core <= cores; core++) {
            ranges[core] = (uint32_t)((uint64_t)core * blocks / cores);
        }
    } else {
        cost_cuts(cores, blocks, ranges, area, total, work->cuts);
        for (uint32_t cut_index = 0; cut_index <= cores; cut_index++) {
            ranges[cut_index] = work->cuts[cut_index];
        }
    }
    for (uint32_t core = 0; core < cores; core++) {
        volatile uint32_t* page = core_page(area, core);
        page[0] = ranges[core];
        page[1] = ranges[core + 1];
    }
    work->ranged[area_index]++;
    return sweep_pages(cores, area, 0, 8);
}
