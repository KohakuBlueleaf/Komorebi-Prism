// Rasterizer on the host CPU: setup and binning over triangles, fill over tiles.
// Usage: raster_cpu --scene DIR --out DIR [--threads N] [--reps R] [--materials DIR]
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <numeric>
#include <string>
#include <vector>

#include "host.hpp"
#include "shade.hpp"

using namespace kr;

struct Buffers {
    std::vector<Record> records;  // (2T): first pieces, then second pieces
    std::vector<uint8_t> pieces;  // per triangle, setup_triangle's bits
    std::vector<int32_t> counts, offsets, list;
    std::vector<int32_t> chunk_counts;  // (tiles, chunks)
    std::vector<float> colour, depth;
    std::vector<int32_t> owner;
};

struct Times {
    double setup, bin, fill;
};

static void for_tiles_of(
    const Record& record,
    int& first_tile_x,
    int& last_tile_x,
    int& first_tile_y,
    int& last_tile_y
) {
    first_tile_x = record.box[0] / TILE;
    last_tile_x = record.box[1] / TILE;
    first_tile_y = record.box[2] / TILE;
    last_tile_y = record.box[3] / TILE;
}

static void fill_tile(Buffers& buffers, int tile) {
    const int tile_x = tile % TILES_X, tile_y = tile / TILES_X;
    const int left = tile_x * TILE, top = tile_y * TILE;
    float depth[TILE * TILE];
    int32_t owner[TILE * TILE];
    float colour[TILE * TILE][3];
    for (int i = 0; i < TILE * TILE; i++) {
        depth[i] = 0.0f;
        owner[i] = -1;
        for (int channel = 0; channel < 3; channel++) {
            colour[i][channel] = background(channel);
        }
    }
    for (
        int entry = buffers.offsets[tile]; entry < buffers.offsets[tile + 1]; entry++
    ) {
        const Record& record = buffers.records[buffers.list[entry]];
        int first_x = std::max(record.box[0], left);
        int last_x = std::min(record.box[1], left + TILE - 1);
        int first_y = std::max(record.box[2], top);
        int last_y = std::min(record.box[3], top + TILE - 1);
        for (int y = first_y; y <= last_y; y++) {
            float py = (float)y + 0.5f;
            for (int x = first_x; x <= last_x; x++) {
                float px = (float)x + 0.5f;
                if (!covers(record, px, py)) {
                    continue;
                }
                int i = (y - top) * TILE + (x - left);
                float inverse_z = depth_at(record, px, py);
                if (nearer(inverse_z, record.triangle, depth[i], owner[i])) {
                    depth[i] = inverse_z;
                    owner[i] = record.triangle;
                    colour_at(record, px, py, colour[i]);
                }
            }
        }
    }
    for (int y = 0; y < TILE; y++) {
        for (int x = 0; x < TILE; x++) {
            int i = y * TILE + x;
            size_t pixel = (size_t)(top + y) * WIDTH + (left + x);
            buffers.depth[pixel] = depth[i];
            buffers.owner[pixel] = owner[i];
            for (int channel = 0; channel < 3; channel++) {
                buffers.colour[3 * pixel + channel] = colour[i][channel];
            }
        }
    }
}

static Times run(const Mesh& mesh, Pool& pool, Buffers& buffers) {
    const int thread_count = pool.size();
    const int tile_count = TILES_X * TILES_Y;
    const int chunk_count = thread_count * 2;
    const int64_t per_chunk = (mesh.triangle_count + chunk_count - 1) / chunk_count;
    Times times;
    double started = now_ms();
    pool.for_chunks(mesh.triangle_count, 256, [&](int64_t first, int64_t end) {
        for (int64_t i = first; i < end; i++) {
            buffers.pieces[i] = ((uint8_t)setup_triangle(
                mesh,
                (int)i,
                buffers.records[i],
                buffers.records[mesh.triangle_count + i]
            ));
        }
    });
    double setup_done = now_ms();
    std::fill(buffers.chunk_counts.begin(), buffers.chunk_counts.end(), 0);
    pool.for_chunks(chunk_count, 1, [&](int64_t chunk, int64_t) {
        int32_t* count = &buffers.chunk_counts[chunk];
        int64_t end = std::min<int64_t>((chunk + 1) * per_chunk, mesh.triangle_count);
        for (int64_t i = chunk * per_chunk; i < end; i++) {
            for (int piece = 0; piece < 2; piece++) {
                if (!((buffers.pieces[i] >> piece) & 1)) {
                    continue;
                }
                const Record&
                    record = (buffers
                                  .records[i + piece * (int64_t)mesh.triangle_count]);
                int first_tile_x, last_tile_x, first_tile_y, last_tile_y;
                for_tiles_of(
                    record, first_tile_x, last_tile_x, first_tile_y, last_tile_y
                );
                for (int tile_y = first_tile_y; tile_y <= last_tile_y; tile_y++) {
                    for (int tile_x = first_tile_x; tile_x <= last_tile_x; tile_x++) {
                        count[(tile_y * TILES_X + tile_x) * chunk_count]++;
                    }
                }
            }
        }
    });
    int32_t total = 0;
    for (int tile = 0; tile < tile_count; tile++) {
        buffers.offsets[tile] = total;
        for (int chunk = 0; chunk < chunk_count; chunk++) {
            int32_t entries = buffers.chunk_counts[tile * chunk_count + chunk];
            buffers.chunk_counts[tile * chunk_count + chunk] = total;
            total += entries;
        }
        buffers.counts[tile] = total - buffers.offsets[tile];
    }
    buffers.offsets[tile_count] = total;
    buffers.list.resize(total);
    pool.for_chunks(chunk_count, 1, [&](int64_t chunk, int64_t) {
        int32_t* cursor = &buffers.chunk_counts[chunk];
        int64_t end = std::min<int64_t>((chunk + 1) * per_chunk, mesh.triangle_count);
        for (int64_t i = chunk * per_chunk; i < end; i++) {
            for (int piece = 0; piece < 2; piece++) {
                if (!((buffers.pieces[i] >> piece) & 1)) {
                    continue;
                }
                const int64_t record_index = i + piece * (int64_t)mesh.triangle_count;
                const Record& record = buffers.records[record_index];
                int first_tile_x, last_tile_x, first_tile_y, last_tile_y;
                for_tiles_of(
                    record, first_tile_x, last_tile_x, first_tile_y, last_tile_y
                );
                for (int tile_y = first_tile_y; tile_y <= last_tile_y; tile_y++) {
                    for (int tile_x = first_tile_x; tile_x <= last_tile_x; tile_x++) {
                        buffers.list[cursor
                                         [(tile_y * TILES_X + tile_x) *
                                          chunk_count]++] = (int32_t)record_index;
                    }
                }
            }
        }
    });
    double bin_done = now_ms();
    std::vector<int> order(tile_count);
    std::iota(order.begin(), order.end(), 0);
    std::stable_sort(order.begin(), order.end(), [&](int first_tile, int second_tile) {
        return buffers.counts[first_tile] > buffers.counts[second_tile];
    });
    pool.for_chunks(tile_count, 1, [&](int64_t rank, int64_t) {
        fill_tile(buffers, order[rank]);
    });
    double fill_done = now_ms();
    times.setup = setup_done - started;
    times.bin = bin_done - setup_done;
    times.fill = fill_done - bin_done;
    return times;
}

// One FILL's frame: colour, 1/z, winner and the tile list sizes.
struct Layer {
    std::vector<float> colour, depth;
    std::vector<int32_t> owner, counts;
};

static Layer fill_layer(
    Mesh mesh, const int32_t* indices, Pool& pool, Buffers& buffers
) {
    mesh.indices = indices;
    run(mesh, pool, buffers);
    return {buffers.colour, buffers.depth, buffers.owner, buffers.counts};
}

struct Shaded {
    std::vector<ShadeTriangle> triangles;
    std::vector<float> colour, depth;
    std::vector<int32_t> owner;
};

// SHADE of a frame on one thread: each pixel takes the masked layer where it is
// nearer and not a hole, else the other layer.
static void shade_frame(
    const Mesh& mesh,
    const Materials& materials,
    const float* light,
    const Layer& opaque,
    const Layer& masked,
    Shaded& out,
    double& setup_ms,
    double& shade_ms
) {
    double started = now_ms();
    for (int triangle = 0; triangle < mesh.triangle_count; triangle++) {
        shade_setup_triangle(mesh, materials, triangle, out.triangles[triangle]);
    }
    double setup_done = now_ms();
    for (int y = 0; y < HEIGHT; y++) {
        float py = (float)y + 0.5f;
        for (int x = 0; x < WIDTH; x++) {
            float px = (float)x + 0.5f;
            size_t pixel = (size_t)y * WIDTH + x;
            float colour[3];
            int owner = masked.owner[pixel];
            bool taken = false;
            if (owner >= 0 &&
                nearer(
                    masked.depth[pixel], owner, opaque.depth[pixel], opaque.owner[pixel]
                )) {
                for (int c = 0; c < 3; c++) {
                    colour[c] = masked.colour[3 * pixel + c];
                }
                taken = (!shade_pixel(
                    mesh,
                    materials,
                    light,
                    out.triangles[owner],
                    owner,
                    masked.depth[pixel],
                    px,
                    py,
                    colour
                ));
            }
            const Layer& layer = taken ? masked : opaque;
            if (!taken) {
                for (int c = 0; c < 3; c++) {
                    colour[c] = opaque.colour[3 * pixel + c];
                }
                if (opaque.owner[pixel] >= 0) {
                    shade_pixel(
                        mesh,
                        materials,
                        light,
                        out.triangles[opaque.owner[pixel]],
                        opaque.owner[pixel],
                        opaque.depth[pixel],
                        px,
                        py,
                        colour
                    );
                }
            }
            out.depth[pixel] = layer.depth[pixel];
            out.owner[pixel] = layer.owner[pixel];
            for (int c = 0; c < 3; c++) {
                out.colour[3 * pixel + c] = colour[c];
            }
        }
    }
    double shade_done = now_ms();
    setup_ms = setup_done - started;
    shade_ms = shade_done - setup_done;
}

// --materials: FILL over the triangles that are not masked and over those that are,
// then SHADE on one thread, timed; tile_counts are both layers' added.
static int main_shaded(
    const Args& args, Mesh& mesh, const float* light, int thread_count, int repetitions
) {
    std::string folder = args.get("materials"), out_folder = args.get("out");
    Array uv = load_npy(folder + "/uv.npy", 4);
    Array material = load_npy(folder + "/material.npy", 4);
    Array light_term = load_npy(folder + "/light.npy", 4);
    Array kind = load_npy(folder + "/kind.npy", 4);
    Array base_colour = load_npy(folder + "/base_colour.npy", 4);
    Array textures = load_npy(folder + "/textures.npy", 4);
    Array exponent = load_npy(folder + "/exponent.npy", 4);
    Array specular = load_npy(folder + "/specular.npy", 4);
    Array texels = load_npy(folder + "/texels.npy", 1);
    Array mip = load_npy(folder + "/mip.npy", 8);
    Array levels = load_npy(folder + "/levels.npy", 4);
    Array linear = load_npy(folder + "/texel_linear.npy", 4);
    Materials materials;
    materials.uv = uv.data<float>();
    materials.material = material.data<int32_t>();
    materials.light = light_term.data<float>();
    materials.kind = kind.data<int32_t>();
    materials.base_colour = base_colour.data<float>();
    materials.textures = textures.data<int32_t>();
    materials.exponent = exponent.data<int32_t>();
    materials.specular = specular.data<float>();
    materials.texels = texels.data<uint8_t>();
    materials.mip = mip.data<int64_t>();
    materials.levels = levels.data<int32_t>();
    materials.linear = linear.data<float>();

    // The two layers' index arrays: the other layer's triangles collapsed to their
    // first corner, so setup drops them and the rest keep their numbers.
    const size_t count = (size_t)mesh.triangle_count;
    std::vector<int32_t> opaque_indices(mesh.indices, mesh.indices + 3 * count);
    std::vector<int32_t> masked_indices(opaque_indices);
    for (size_t triangle = 0; triangle < count; triangle++) {
        bool is_masked = materials.kind[materials.material[triangle]] == KIND_MASKED;
        int32_t* collapse =
            ((is_masked ? opaque_indices.data() : masked_indices.data()) +
             3 * triangle);
        collapse[1] = collapse[2] = collapse[0];
    }
    Pool pool(thread_count);
    Buffers buffers;
    const int tile_count = TILES_X * TILES_Y;
    buffers.records.resize(2 * count);
    buffers.pieces.resize(count);
    buffers.counts.resize(tile_count);
    buffers.offsets.resize(tile_count + 1);
    buffers.chunk_counts.resize((size_t)thread_count * 2 * tile_count);
    buffers.colour.resize((size_t)WIDTH * HEIGHT * 3);
    buffers.depth.resize((size_t)WIDTH * HEIGHT);
    buffers.owner.resize((size_t)WIDTH * HEIGHT);
    Layer opaque = fill_layer(mesh, opaque_indices.data(), pool, buffers);
    Layer masked = fill_layer(mesh, masked_indices.data(), pool, buffers);

    Shaded shaded;
    shaded.triangles.resize(count);
    shaded.colour.resize((size_t)WIDTH * HEIGHT * 3);
    shaded.depth.resize((size_t)WIDTH * HEIGHT);
    shaded.owner.resize((size_t)WIDTH * HEIGHT);
    double setup_ms, shade_ms;
    shade_frame(mesh, materials, light, opaque, masked, shaded, setup_ms, shade_ms);
    RepLog log(repetitions);
    for (int repetition = 0; repetition < repetitions; repetition++) {
        shade_frame(mesh, materials, light, opaque, masked, shaded, setup_ms, shade_ms);
        char record[256];
        std::snprintf(
            record,
            sizeof record,
            "{\"shade_setup_ms\": %.4f, \"shade_ms\": %.4f, \"total_ms\": %.4f}",
            setup_ms,
            shade_ms,
            setup_ms + shade_ms
        );
        log.add(record);
    }
    double loop_ms = log.finish();
    std::printf(
        "{\"impl\": \"cpu\", \"threads\": 1, \"fill_threads\": %d, "
        "\"triangles\": %d, \"reps_n\": %d, \"loop_ms\": %.4f, \"reps\": [%s]}\n",
        thread_count,
        mesh.triangle_count,
        repetitions,
        loop_ms,
        log.body.c_str()
    );
    if (!out_folder.empty()) {
        std::vector<int32_t> counts(tile_count);
        for (int tile = 0; tile < tile_count; tile++) {
            counts[tile] = opaque.counts[tile] + masked.counts[tile];
        }
        save_f32(out_folder + "/colour.npy", shaded.colour.data(), {HEIGHT, WIDTH, 3});
        save_f32(out_folder + "/depth.npy", shaded.depth.data(), {HEIGHT, WIDTH});
        save_i32(out_folder + "/tri.npy", shaded.owner.data(), {HEIGHT, WIDTH});
        save_i32(out_folder + "/tile_counts.npy", counts.data(), {TILES_Y, TILES_X});
    }
    return 0;
}

int main(int argc, char** argv) {
    Args args(argc, argv);
    std::string scene = args.get("scene"), out_folder = args.get("out");
    int thread_count = args.geti("threads", (int)std::thread::hardware_concurrency());
    int repetitions = args.geti("reps", 3);
    Array positions = load_npy(scene + "/positions.npy", 4);
    Array colours = load_npy(scene + "/colors.npy", 4);
    Array indices = load_npy(scene + "/indices.npy", 4);
    Array camera = load_npy(scene + "/camera.npy", 4);
    Mesh mesh;
    mesh.positions = positions.data<float>();
    mesh.colors = colours.data<float>();
    mesh.indices = indices.data<int32_t>();
    mesh.triangle_count = (int)indices.shape[0];
    std::copy(camera.data<float>(), camera.data<float>() + 16, mesh.camera);
    if (!args.get("materials").empty()) {
        Array light = load_npy(scene + "/light.npy", 4);
        return main_shaded(args, mesh, light.data<float>(), thread_count, repetitions);
    }

    Pool pool(thread_count);
    Buffers buffers;
    const int tile_count = TILES_X * TILES_Y;
    buffers.records.resize(2 * (size_t)mesh.triangle_count);
    buffers.pieces.resize(mesh.triangle_count);
    buffers.counts.resize(tile_count);
    buffers.offsets.resize(tile_count + 1);
    buffers.chunk_counts.resize((size_t)thread_count * 2 * tile_count);
    buffers.colour.resize((size_t)WIDTH * HEIGHT * 3);
    buffers.depth.resize((size_t)WIDTH * HEIGHT);
    buffers.owner.resize((size_t)WIDTH * HEIGHT);

    run(mesh, pool, buffers);  // warm-up: page faults, thread start
    RepLog log(repetitions);
    for (int repetition = 0; repetition < repetitions; repetition++) {
        Times times = run(mesh, pool, buffers);
        char record[256];
        std::snprintf(
            record,
            sizeof record,
            "{\"setup_ms\": %.4f, \"bin_ms\": %.4f, \"fill_ms\": %.4f, \"total_ms\": "
            "%.4f}",
            times.setup,
            times.bin,
            times.fill,
            times.setup + times.bin + times.fill
        );
        log.add(record);
    }
    double loop_ms = log.finish();
    int valid = 0;
    for (uint8_t bits : buffers.pieces) {
        valid += (bits & 1) + (bits >> 1);
    }
    std::printf(
        "{\"impl\": \"cpu\", \"threads\": %d, \"triangles\": %d, \"reps_n\": %d, "
        "\"loop_ms\": %.4f, \"valid\": %d, \"entries\": %d, \"reps\": [%s]}\n",
        thread_count,
        mesh.triangle_count,
        repetitions,
        loop_ms,
        valid,
        buffers.offsets[tile_count],
        log.body.c_str()
    );
    if (!out_folder.empty()) {
        save_f32(out_folder + "/colour.npy", buffers.colour.data(), {HEIGHT, WIDTH, 3});
        save_f32(out_folder + "/depth.npy", buffers.depth.data(), {HEIGHT, WIDTH});
        save_i32(out_folder + "/tri.npy", buffers.owner.data(), {HEIGHT, WIDTH});
        save_i32(
            out_folder + "/tile_counts.npy", buffers.counts.data(), {TILES_Y, TILES_X}
        );
    }
    return 0;
}
