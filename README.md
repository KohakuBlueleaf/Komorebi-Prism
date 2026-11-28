# Komorebi-Prism

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-4C9989)](LICENSE)

**A real-time renderer on Tenstorrent Blackhole cards, built on Komorebi: tile-resident
and matrix-heavy. glTF in, frame out.**

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/teaser-dark.svg">
  <img src="docs/images/teaser-light.svg" width="880" alt="You give it: the commands prism_cli open with a glTF file and prism_viewer.server with --pipeline gi_threads; the preset configs/pipeline/gi_threads.py, which names an implementation for each item of the pipeline; the light stage's Step, which reads and leaves planes kept in L1, and the tile thread LIT; the pull (kmx_pull_run on X280 1, port.next on a core); the transport's apply y = M x (sums in L1 on 32 x 32 tiles, matmul_block) and the field update's graph, whose last command gives X280 1 the new field. The card draws it by itself: 120 Tensix cores, each inside a tile thread, asking X280 1 for threads; X280 2 and 3 run the job thread's graph, an apply on every core between two frames; the display pages leave; one core runs visibility, material_lit, light, post with frame.visibility and frame.surface in its L1. One gi_threads frame on Sponza: 20.00 ms moving (count 1.08, sums 0.32, place 1.88, then the tile), 16.80 ms standing, against the stage-wise gi less its push, 24.12 ms; after a sun move (3 bounces) gi_threads draws 5 frames and shows the new field at 161.4 ms, where gi stops for 173.4 ms; each of ten scenes' gi_threads frame over gi less push, 0.38 to 0.74 standing. What comes out: gi_threads frames of Sponza (16.80 ms), Bistro interior (21.15 ms), Breakfast Room (14.06 ms) and Italian Flat (29.68 ms, at the camera of the Cycles comparison); 0 pixels different from gi in 3,840 frames; 37.75 ms standing on the 29.8 M-triangle scene against 100.58 for gi less push; 57.08 ms standing at 3,840 x 2,160; Italian Flat at 29.68 ms a frame, where Cycles reading the same glTF takes 43.4 s for 256 samples on one V100-class GPU.">
</picture>

*What you give it, real lines of the files each card names, marked in the colour of what it
causes on the card; the card running a frame by itself and the field's update beside the
frames; real `gi_threads` frames and what each number is compared with. One P150A, 1,920 x
1,080, the median frame on the card at each scene's view
([gi_threads](measurements/gi_threads/README.md)); the pictures from the viewer at 1,920 x
1,080, Italian Flat's at the camera of its comparison with Cycles reading the same glTF
file ([glTF truth](docs/performance/gltf_truth.md)); every `gi_threads` picture equal to
`gi`'s.*

A frame is drawn by the card alone. The host writes the camera and sends one command,
FRAME, to a thread on the card's X280 cores, **the frame's thread**. It cuts the view's
work into threads and hands them out by **pulls**: every Tensix core asks for the next
one when it has finished its last, until none is left. The renderer is
**tile-resident**: the core that takes a tile's thread runs every step of that tile
(visibility, material, light, display) with the tile's planes kept in its own memory
between the steps, and writes only the tile's finished display page. It is
**matrix-heavy** where the light bounces: global illumination is a scene's
light-transport matrix, stored as a hierarchical matrix of dense and low-rank blocks and
applied with the cores' matrix engines; the field it makes is updated on the card when
the sun moves, by a thread of its own while the frames go on.

What is here: glTF scenes opened into the renderer's tables; visibility of the opaque,
masked and glass layers; textured materials; direct light from the sun with its shadow
map, the lamps and the sky; indirect light from a field the card updates itself; the
frame converted for display on the card. A command line, a loop that keeps a pipeline
loaded, and a viewer in the browser drive it. Every algorithm has a numpy reference, and
every frame is judged against the reference's picture. No release has been made; the
version is 0.0.0.

## Quick start

From a clone installed as in [Install](#install), on card 0: open a glTF file, draw it,
and steer the camera in the viewer.

```sh
export PRISM_DATA=$HOME/prism-data
python -m prism_cli open scene.glb --pipeline gi_threads --size 1920 1080 --card 0 --out out
python -m prism_cli run --pipeline gi_threads --scene NAME --view camera --size 1920 1080 \
    --frames 64 --path forward --card 0
python -m prism_viewer.server --host 127.0.0.1 --port 8790 --token TOKEN \
    --pipeline gi_threads --scene NAME --view camera --card 0
```

`open` converts the file once into the data root (a second `open` of the same file
converts nothing), makes its lights when it has none, draws 16 frames from the file's
camera and writes the last picture into `out/`; its one-line JSON record names the scene
(`NAME`, the file's stem and ten hex digits of a digest of the file's bytes and the
converter's version: a new converter gives a scene a new name, as in the tables below). `run` draws 64 frames with the eye moving
forward. A scene just opened has no far field yet: `open` starts its build on the host
beside the frames, and `gi_threads` draws without the indirect light (the record's
`far_field` says so) until the build has written its files; the next load, or the
viewer by itself, draws with it, and `open --wait-far-field` waits for the build and
draws again.
The viewer, once its page is built
(`cd apps/prism_viewer/web && npm install && npm run build`), is at
`http://127.0.0.1:8790/?token=TOKEN`. Every step, and the public scenes, are in [the quick start](docs/guides/quick_start.md).

## Install

**The machine.** Linux on x86-64, Python 3.13, and a Tenstorrent Blackhole P150A card
with Tenstorrent's kernel driver (`tenstorrent`) and the card's firmware. The runs in the
measurements were made with driver 2.12.0 and firmware bundle 19.13.1.0. The driver maps
a 1 GiB hugepage for each card into the process that opens it, the host channel; the
stage-wise presets push each frame's picture into it, and a session without it refuses
the push. Tenstorrent's `tt-smi` resets a card (`tt-smi -r 0`). Making the scenes' data
also needs a C++ compiler (`g++`), and the viewer's page needs Node.js and npm. One
process at a time can open a card; a second one is refused at once with the first one's
process id.

**The Python packages.** `pip install` brings all of these from PyPI. No tt-metal source
tree, `ttnn` or `torch` is needed.

| Package | What it brings |
|---|---|
| `komorebi-tt` 0.6.0 or later | Komorebi, the framework the card's programs are written in, and its command `kmr` |
| `komorebi-runtime`, through `komorebi-tt`'s extra `runtime` | Tenstorrent's tt-metal, built and pinned: its libraries, the cores' runtime, the X280 runtime, the locator for the RISC-V compiler |
| `numpy` | every array on the host |
| `pillow` (the extras `viewer` and `scenes`) | the viewer's JPEG frames; decoding the scenes' textures |

Leave `TT_METAL_HOME` unset: when it is set, Komorebi uses that tt-metal tree instead of
the runtime package. Install from a clone, because the presets, the kernels' sources and
the viewer's page are read from it:

```sh
git clone https://github.com/KohakuBlueleaf/Komorebi-Prism && cd Komorebi-Prism
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[viewer,scenes]"    # komorebi-tt and its runtime come from PyPI
kmr setup --card 0                   # once per card
```

`kmr setup --card 0` fetches the RISC-V compiler the runtime names and prepares card 0's
X280 memory, then asks for one reset (`tt-smi -r 0`); the preparation survives later
resets. `kmr doctor` checks the setup without opening the card. Komorebi keeps the
compiler, the runtime and its builds in `~/.cache/komorebi` (`KMR_CACHE` names another
folder); the first run of a preset compiles the card's program, so it starts slower than
later runs. The variables are in [the environment](docs/guides/environment.md).

## The renderer

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/levels-dark.svg">
  <img src="docs/images/levels-light.svg" width="880" alt="The renderer at three levels. 1, the machine: the host joined by PCIe to one Blackhole P150A, its eight DRAM banks D0 to D7, X280 cluster 0 (Komorebi's dispatcher), cluster 1 (the frame's thread) and clusters 2 and 3 (the job thread), and 120 Tensix cores coloured by their port on X280 1: ranks 0 to 29, 30 to 59, 60 to 89, 90 to 119; an update's applies in gi_threads run on every rank between two frames. 2, a frame: one view as six columns, each with what X280 1 does, what the Tensix cores do and what is left in DRAM: count (a pull of ranges of triangle blocks, 4 on Sponza, those outside the view skipped; counts and rows pages), sums (an ordinary command; records and the slices' words), running sum (on the X280; the slices' places), place (a pull replaying the log; each layer's lists), words (on the X280; the frame's page), tile (a pull answered by dp_choose; display pages). 3, one core: its port on X280 1, mover A (asks, reads the record, hands on the descriptor), mover B, the rings frame_jobs and frame_list_a and _b, the compute CPUs unpack, math and pack running visibility, material_lit, light and post, and its L1: the shared line of 1,216 bytes, the steps' kept state, frame.visibility and frame.surface of 20 pages of 4 KiB each; the display page is the one write.">
</picture>

*The same renderer at three levels, each zoomed from the one above: the card and who sits
where; a frame as the view's pulls and what each leaves in DRAM; one core running a tile
thread with the tile's planes in its L1.*

| step | what it computes | where it runs |
|---|---|---|
| count, place | each layer's triangles counted into the tiles their boxes reach, then written into the tiles' lists; a range of triangle blocks a thread, its size chosen from the scene, a range outside the view skipped; at a standing camera the lists are kept and neither runs | the Tensix core that takes the range |
| sums | each slice of 16 tiles: its records (a tile thread each) in order of weight, every core's positions | every Tensix core, one command |
| running sum, the tile pull's choice | each layer's list place a slice; the next tile thread for the core that asks | the frame's thread, X280 cluster 1 |
| `visibility` | each layer's planes: 1/z, colour, triangle number, from the tile's lists | the core that takes the tile thread |
| `material`, `material_lit` | the material's colour or texel, the masked layer cut and merged, the glass layer blended; with lights, each layer's surface | the same core |
| `light` | the sun through its shadow map's filter, the lamps, the specular terms, the sky, the indirect field, emissive, the background, the tone step | the same core |
| `post` | the colour as 8-bit pixels, written to the tile's display page | the same core |
| the sun's shadow map | DEPTH views of the sun at each load and after it moves: `visibility`, `material_lit`, `depth_out` | the frame's thread hands them out; the Tensix cores draw them |
| the indirect field | the sources, a transport apply a bounce, the field's pages; swapped in between two frames | the job thread, X280 clusters 2 and 3; the applies on every core, between two frames |

The parts, the slots between them and the presets are in
[the renderer](docs/concepts/renderer.md); who hands out what and what a core keeps in
[the frame as threads](docs/concepts/threads.md); the indirect light in
[light transport](docs/concepts/light_transport.md).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/pipeline-dark.svg">
  <img src="docs/images/pipeline-light.svg" width="880" alt="The pipeline: the items raster (step visibility), material (step material_lit), direct (step light) and post (step post) in a row, the slots between them: scene.mesh and view.camera into raster; frame.visibility and frame.lists from raster to material; frame.surface and mesh.attributes from material to direct; the colour planes to post; display.picture out. Above direct, the shadow, the sun's DEPTH views (visibility, material_lit, depth_out), giving light.shadow_map; below it, indirect, the field from the transport's apply a bounce on the job thread, giving light.field from elements.radiance and elements.irradiance. Below, a table of which implementation fills each item in the presets textured_threads, lit_threads and gi_threads (raster.threads, material.texture.threads, direct.shadow_pcf, direct.light.threads or direct.light.threads_field, indirect.transport.threads and indirect.field_update.threads, post.show.threads) and textured, lit and gi (raster, material.texture, direct.shadow_pcf, direct.light, indirect.transport and indirect.field_update, post.show); gi_threads also names indirect.near_tile, which fills no item: the one-tile indirect product, a step of the tile thread with the option near_tile, off by default.">
</picture>

*The items, the named slots between them and the step each gives the tile thread; the slots
drawn yellow are planes that stay in a core's L1 in the threads' form. A preset chooses which
implementation fills each item.*

The presets in [configs/pipeline](configs/pipeline): `gi_threads` is the renderer;
`lit_threads` is it without the indirect light, `textured_threads` without any light; `textured`, `lit` and `gi` run the same parts
stage-wise, as commands on every core one after another, and draw the pictures the
threads' presets are judged by; `raster`, `lit_tile`, `gi_tile`, `field` and `apply` are
parts and comparisons. `gi_threads`' option `near_tile` (off by default) takes a standing
frame's indirect light from one matrix product a screen tile, run on the matrix engine,
in place of the field's lookup ([near field](docs/internals/reference/near_field.md)).

### The frame as threads

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/threads-dark.svg">
  <img src="docs/images/threads-light.svg" width="880" alt="One frame of Sponza's overview, 1,920 x 1,080, lit, on 11 of the 120 cores, both forms on one time axis in ms. Above, lit_threads with the tile pull's choice prefer, 14.584 ms: X280 1 answers the asks; each core takes 15 to 21 count ranges in the count pull (1.04 ms), one core runs the sums, each core takes place ranges in the place pull (1.92 ms; core 55 holds one long range), then 14 to 20 tile threads in the tile pull (11.30 ms), each bar split into visibility, material_lit, light and post; the cores end at different times and the pull ends with the last tile thread. Below, the stage-wise lit, 18.838 ms: every core runs count, sums, place, set-up, fill, shade, light and show as commands one after another, each core standing still at each command's end until the slowest is done; the X280's middle pass (2.028 ms) holds every core; the push ends the frame.">
</picture>

*The same frame both ways on one axis. Threads: a core takes its next thread as soon as its last
ends, so it stands still only at a pull's end. Stage-wise: every command waits for its slowest
core. Phase and command times measured ([threads_account](measurements/threads_account/README.md),
[account](measurements/account/README.md)); where each core's threads lie inside a phase is drawn
to the measured counts and spans, not taken from one record.*

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/resident-dark.svg">
  <img src="docs/images/resident-light.svg" width="880" alt="Tile-resident, Sponza's overview, 1,920 x 1,080, lit, a frame over all cores. Above, stage-wise: FILL 2.397 ms writes 83.56 MB of planes to DRAM; SHADE 6.061 ms reads 320.58 MB and writes 98.89 MB; LIGHT 3.099 ms reads 174.12 MB and writes 25.07 MB; SHOW 1.542 ms reads 25.07 MB and writes 8.36 MB; PUSH 0.564 ms sends 8.36 MB to the host; each command on every core, waiting for the slowest. Below, lit_threads: one Tensix core runs one tile thread's steps visibility (2.77 ms a frame a core), material_lit (4.91), light (2.93) and post (0.05) with frame.visibility (20 x 4 KiB) kept in L1 from visibility to post and frame.surface (20 x 4 KiB) from material_lit to light; it reads lists (83.48 MB a frame) and texture and light pages (276.41 MB) and writes only the display pages (8.36 MB); 2,040 tile threads a frame, each on the core that asks next.">
</picture>

*Tile-resident: the core that took a tile keeps the tile's planes in its L1 through every
step and writes only the finished display page; the stage-wise form writes the frame's planes
to DRAM between its commands (207.52 MB a frame) and reads them back. Stage-wise bytes and
times by command from [account](measurements/account/README.md); the threads' bytes by path
and pack's time a step from [threads_account](measurements/threads_account/README.md).*

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/dispatch-dark.svg">
  <img src="docs/images/dispatch-light.svg" width="880" alt="How work reaches a core. The cut: a layer's triangle blocks of 32 triangles in count ranges of 4 blocks on Sponza, the size set by the scene; a row of the frame's 60 tiles in slices of 16; slice 1's records in order of weight, numbered slice x 32 + place, a tile past the weight heavy cut into bands of rows. A pull: mover A tells its port on X280 1 the ended thread's number, cost and codes, and asks; the answer, a record's number and its word, is usually waiting (0.3 us); mover A hands the descriptor to the compute CPUs and mover B and takes one more ahead; an answer of 0 means none left. The tile pull's choice: prefer (a slice within one of the core's last, heaviest first) 9.930 ms, order (the next slice with records left, one cursor) 10.647 ms, kept (slice s to core s mod cores; 136 slices on 120 cores, 16 cores take two) 20.243 ms, Sponza textured. Lists too small: the running sum finds a layer's entries past its list slots, the view stops with DP_LISTS_SMALL before place writes, the need page goes to DRAM, the host's ThreadsHost.needed makes lists of the entries and a quarter more, writes the rows again and keeps list_slots_least, and the frame is tried again; past the build's capacity, DP_TOO_MANY, one reload.">
</picture>

*Work reaches a core only when it asks: the frame is cut into ranges, slices and records;
each ask is answered from its port on X280 1; the tile pull's policy chooses the record; a
list too small is grown while the run stays loaded. Tile pull times: Sponza's overview,
textured ([threads_account](measurements/threads_account/README.md)).*

## The light

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/transport-dark.svg">
  <img src="docs/images/transport-light.svg" width="880" alt="The indirect light is one matrix product y = M x applied as 32 x 32 tiles on the cores' matrix engines. First, Sponza's transport matrix as it is stored, 1,151 x 1,151 tiles of 32 elements: dense near blocks along the diagonal (13,024 blocks, 265,798 tiles), low-rank far blocks U V^T (8,406 blocks, 155,628 tiles) and dropped zero blocks; three blocks picked out: a dense 5 x 5 block as 25 tile products, a 9 x 9 low-rank block of rank 19 as t = V^T x then U t in 18 tile products instead of 81, and a 72 x 72 far block of rank 94 stored as 432 tiles instead of 5,184. Second, the apply as one command on every core: y's receiver tiles dealt in contiguous ranges, one a core, 3 to 16 tiles each at about 4,500 weight tiles to read; inside one core, mover A reads the table pages and streams x and the bfp8_b weights from DRAM, the compute CPUs unpack, multiply tile by tile with matmul_block and pack onto the core's own sums in L1, mover B writes y's tiles; one apply takes 2,609.3 us on Sponza. Third, the bounces: the sources L0, E1 = M L0, then Ek = M (albedo / pi Ek-1) for each pass of the scene's count, their sum with the sky into the field.">
</picture>

*The light transport. Sponza's matrix is drawn from its transport set on 128 x 128
cells, each cell the kind holding most of its tiles; the ranges are the deal of its
receivers over 120 cores. The apply's time: one P150A, 120 cores, AICLK 1,350 MHz,
32 calls ([measurements/apply](measurements/apply/README.md)).*

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/field-dark.svg">
  <img src="docs/images/field-light.svg" width="880" alt="The field turns the elements' light into voxels a pixel reads, and the card makes it again beside the frames. First, a section of a room's corner: voxels of side h, the element spacing; one voxel near the corner gathers, for each of its six directions, the elements within 2h that its centre sees, one hidden behind a box left out; its texel is 32 bits, a has-data bit and red, green and blue square-root codes of 11, 11 and 9 bits; a pixel P with normal n reads the 8 voxel centres around Q = P + n h / 2. Second, after the sun is set: the frame's thread draws the sun's pass and then five frames with the old field on every rank, while the job thread on X280 clusters 2 and 3 runs field_sources, an apply on every rank between two frames and field_pass for each bounce, then field_finish and field_scale, writing half B of the field's pages; job_wants hands half B and its scale to the frame's thread and the next frame reads it. The stage-wise gi draws no frame until its update is done. Sponza: 5 frames during the update at 18.63 to 19.55 ms against 18.70 steady, two applies of 2.60 ms between frames, the new field's first frame ending 145.3 ms after the job thread's first command.">
</picture>

*The field and its update. Sponza's field: 72,367 voxels of side 50.3, 1.08 million
weights ([the indirect reference](docs/internals/reference/indirect.md)). The update's
numbers: one P150A, 1,920 x 1,080, the sun set to (120, 40) once
([gi_threads](docs/performance/gi_threads.md)); the time axis is schematic.*

How the light is computed, part by part, is in
[light transport](docs/concepts/light_transport.md).

## Results

<img src="docs/guides/viewer/gi_threads_sponza.jpg" width="49%" alt="gi_threads on Sponza's overview, 1,920 x 1,080, from the viewer"> <img src="docs/guides/viewer/gi_threads_bistro_interior.jpg" width="49%" alt="gi_threads on the Bistro interior's overview, 1,920 x 1,080, from the viewer">
<img src="docs/guides/viewer/gi_threads_breakfast_room.jpg" width="49%" alt="gi_threads on the Breakfast Room's overview, 1,920 x 1,080, from the viewer"> <img src="docs/guides/viewer/gi_threads_page_light_1600.jpg" width="49%" alt="The viewer's page with gi_threads on the Bistro interior: the pipeline, scene and camera on the left, the frame, the controls on the right">

*Frames of `gi_threads` from [the viewer](docs/guides/viewer.md), 1,920 x 1,080 on one
P150A, at each view's own pose and the default sun: Sponza, the Bistro interior, the
Breakfast Room, and the viewer's page on the Bistro interior. Crytek Sponza, (c) 2010
Frank Meinl, Crytek, CC BY 3.0; Amazon Lumberyard Bistro, (c) 2017 Amazon Lumberyard,
CC BY 4.0 (Open Research Content Archive); Breakfast Room by Wig42 (Blend Swap),
CC BY 3.0; all three from Morgan McGuire's Computer Graphics Archive.*

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/results-dark.svg">
  <img src="docs/images/results-light.svg" width="880" alt="Two bar charts. First, the frame in ms on ten scenes at 1,920 x 1,080: gi less its push, gi_threads while the camera moves and while it stands; standing, gi_threads takes 0.38 (37.8 against 100.6 ms on lynxsdesign_6efc48febc, 29.8 million triangles) to 0.74 (18.4 against 24.9 on modern_hall) of gi less its push, and moving 0.67 to 0.84. Second, a glTF file's load with gi_threads in seconds to the first picture, cold and warm: classroom (1.25 million triangles) 67.4 and 13.7, italian_flat (4.8 million) 75.5 and 17.0, lynxsdesign (29.8 million) 122.2 and 33.4.">
</picture>

*The frame and the load. The frame: the table below. The load: `prism_cli open` with
`gi_threads`, cold (the file converted, the caches empty, the program built; drawn without
the far field, which is built on the host after it) and warm (the far field built, the
program found), main at f614f61
([measurements/open](measurements/open/README.md#gi_threads-from-the-file)).*

**The renderer's frame.** `gi_threads` against its stage-wise form `gi`: one Blackhole
P150A, 120 cores, AICLK 1,350 MHz, its link at 16 GT/s, Komorebi 0.6.0, 2026-11-28,
1,920 x 1,080, 64 frames at the view's camera, the median over frames 2 to 64, then over
three runs, in ms; every `gi_threads` picture equal to `gi`'s byte for byte. `gi` pushes
its picture into the host's memory inside its frame (0.564 ms) and `gi_threads` does
not, so the like frame is `gi` less its push; each ratio is `gi_threads` over it
([gi_threads](docs/performance/gi_threads.md)). `gi_threads` keeps a frame's lists while
the view does not change (on by default; its option `keep_lists` false makes them again
every frame), so a standing camera's frame is the tile pull alone; while the camera
moves, the count, sums and place pulls run first. The headline is the standing frame,
what a viewer shows most of the time; the moving frame is the cost while the camera
moves.

| scene (view) | `gi` less push | `gi_threads`, camera moves | `gi_threads`, camera stands | ratio moves | ratio stands |
|---|---:|---:|---:|---:|---:|
| sponza (overview) | 24.125 | 20.003 | 16.795 | 0.83 | 0.70 |
| bistro_interior (overview) | 35.663 | 25.247 | 21.154 | 0.71 | 0.59 |
| breakfast_room (overview) | 19.421 | 16.341 | 14.056 | 0.84 | 0.72 |
| salle_de_bain (overview) | 23.344 | 19.696 | 16.010 | 0.84 | 0.69 |
| modern_hall (overview) | 24.893 | 19.384 | 18.370 | 0.78 | 0.74 |
| modern_living_room (overview) | 26.956 | 20.089 | 15.149 | 0.75 | 0.56 |
| classroom_3f4180c5d0 (camera) | 34.017 | 26.514 | 22.037 | 0.78 | 0.65 |
| lynxsdesign_b49574c042 (camera) | 58.016 | 43.664 | 29.433 | 0.75 | 0.51 |
| italian_flat_69651f32b4 (camera) | 52.324 | 40.904 | 29.680 | 0.78 | 0.57 |
| lynxsdesign_6efc48febc (camera) | 100.578 | 67.163 | 37.753 | 0.67 | 0.38 |

The four artists' scenes have 1.25, 8.8, 4.8 and 29.8 million triangles. On the largest
the count and place pulls take 29.1 ms of the moving frame. At 3,840 x 2,160 on Sponza
`gi_threads` takes 57.1 ms standing and 66.5 ms moving (`gi` does not fit in L1 at that
size). After a sun move `gi` stops for 173.4 to 350.9 ms (on the largest scene its run
did not end within 900 s); `gi_threads` draws 4 to 19 frames during its update (the
scene's own count of passes, 2 to 15), the first at the moving frame's time, the others
at the steady frame's.

**The threads' frame against the stage-wise frame, by preset.** One Blackhole P150A, 120 cores,
AICLK 1,350 MHz, 2026-11-27, 1,920 x 1,080, 16 frames at the scene's camera: the median
over frames 2 to 16, then over three runs, in ms. Every frame's picture equal to the
stage-wise frame's (0 pixels different). The threads' frame with the tile pull's
default choice `prefer`; the rows marked (a) were built with the account, which costs
about 1 % ([measurements/threads_account](measurements/threads_account/README.md)).

| scene | list entries a frame | `textured` stage-wise | `textured_threads` | `lit` stage-wise | `lit_threads` |
|---|---:|---:|---:|---:|---:|
| Sponza, overview | 293,571 | 16.428 | 13.134 | 18.838 | 14.584 (a) |
| classroom | 668,006 | 23.216 | 23.469 (a) | | |
| lynxsdesign | 2,072,780 | 42.843 | 45.050 (a) | 48.640 | 44.571 (a) |
| hidden alley | 2,564,913 | 53.544 | 61.899 (a) | 57.700 | 49.396 (a) |

On the artists' scenes the threads' `textured` frame is slower: one heavy tile thread ends
the tile pull (34.5 ms on hidden alley), because the threads' presets cut no tile into
bands (`heavy` 0). Cut at a weight taken from the frame's data, hidden alley `textured` is
53.663 ms and classroom 18.687 ms. Where the frame's time goes, pull by pull and core by
core, is in [the account](docs/performance/account.md).

**The stage-wise presets by scene and size.** One P150A at AICLK 1,350 MHz, its link at
16 GT/s, 2026-11-26, the scenes' overviews; the card frame (the median of a run's
frames, from FRAME to the picture pushed into the host's memory), in ms:

| preset | scene | 1,024 x 1,024 | 1,280 x 720 | 1,920 x 1,080 |
|---|---|---:|---:|---:|
| `raster` | sponza | 4.962 | 4.673 | 7.813 |
| `raster` | bistro_interior | 7.984 | 8.234 | 11.570 |
| `raster` | bistro_exterior | 13.340 | 12.513 | 16.740 |
| `textured` | sponza | 10.781 | | |
| `textured` | bistro_interior | 15.442 | | |
| `textured` | bistro_exterior | 27.688 | | |
| `lit` | sponza | 12.050 | 10.882 | 18.952 |
| `lit` | bistro_interior | 18.136 | 18.342 | 28.914 |
| `lit` | bistro_exterior | 27.947 | 26.116 | 38.958 |
| `gi` | sponza | 14.267 | 12.800 | 23.177 |
| `gi` | bistro_interior | 20.987 | 20.721 | 33.894 |
| `gi` | modern_hall | 13.734 | 12.043 | 24.567 |

Outside the frame, on Sponza at 1,024 x 1,024: the sun's first pass of a run 19.18 ms, the
field's update of `gi` 124.87 ms at 2 bounces, the transport's apply alone 2,609.3 us.
Every number with its check is in [frames](docs/performance/frames.md); the update beside
the frames in [measurements/update_beside](measurements/update_beside/README.md); a glTF
file's load, cold and warm, in [load](docs/performance/load.md); the card's picture
against Cycles reading the same glTF file in [glTF truth](docs/performance/gltf_truth.md).

## The scenes

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/scene-dark.svg">
  <img src="docs/images/scene-light.svg" width="880" alt="A glTF file into the renderer's tables and tensors. First, prism_cli open reads the file's triangle primitives, materials and textures, lights, cameras and nodes (Draco, meshopt and BasisU are refused), converts it once on the host into the data root (digest, import, flatten, materials, textures, writing, shared_vertices, uv, entry; the mesh, materials and lighting files), and the stages' hosts make their tables, written to the card at the load: raster's mesh blocks of 32 triangles and list pages (4,788 MB for Italian Flat with lit), material.texture's texture pages of 32 x 32 texels (487 MB), direct.light's table and light pages (69 MB), post.show's display pages (9 MB), and with the far field the transport's bfp8_b weights and the field's pages. Second, the far field: the open draws gi_threads without the indirect light and says so; public_scenes.py indirect builds the indirect file and the transport set on the host (Sponza 78 s, an artists' scene of 8.8 million triangles 163 s); the next load finds them and draws with the indirect light.">
</picture>

*A glTF file opened. The seconds and megabytes: one P150A, 8 or 24 CPUs of the host,
2026-11-26 and 27 ([measurements/open](measurements/open/README.md),
[measurements/transport_build](measurements/transport_build/README.md)).*

| kind | which | how they come |
|---|---|---|
| public scenes | `sponza`, `bistro_interior`, `bistro_exterior`, `conference`, `breakfast_room`, `salle_de_bain`, `modern_hall`, `modern_living_room` | downloaded from their sources and converted by `scripts/data/public_scenes.py`, each under its own licence ([scenes](docs/concepts/scenes.md)) |
| glTF files | any `.glb` or `.gltf`; measured on artists' scenes of 1.25 to 29.8 million triangles (classroom, italian_flat, lynxsdesign, hidden_alley) | `python -m prism_cli open FILE` ([glTF scenes](docs/guides/gltf_scenes.md)); Blender scenes exported by the workbench ([artists' scenes](docs/guides/artist_scenes.md)) |
| generated scenes | `tiny`, `s10k`, `s100k`, `s1m` | `scripts/data/generated_scenes.py`; vertex colours only (`raster`) |

## Limits

- **One card.** A run uses one P150A (`--card`).
- **What a scene's materials and lights keep**: no refraction, no glass behind glass (one
  transparent layer, the nearest), no coloured shadows, no mirrors or metals'
  reflections; masked, blended and transmitting surfaces cast opaque shadows; sheen and
  clearcoat are dropped; a Blender view transform (AgX, Filmic and their looks) is drawn
  on the card when the scene's sidecar carries its tables, otherwise the display is a
  power transfer (2.2) or the standard sRGB one
  ([scenes](docs/concepts/scenes.md#limits), [the view on the card](docs/internals/post/show.md#a-files-view-transform-on-the-card),
  [glTF truth](docs/performance/gltf_truth.md)).
- **32 lamps a scene.** LIGHT's table holds 32 lamps (`kLampsMax`); a scene with more is
  refused when its lamps are lit.
- **No tile is cut in the threads' presets** (`heavy` 0): a tile with far more entries
  than the others is one tile thread and can end the tile pull. A weight that follows the
  frame's data on the card is not in the threads' form.
- **A scene opened from glTF has no far field** until its transport is built: the
  first open starts the build of the indirect file and the transport set on the host,
  beside the frames, once per scene (Sponza: 78 s block by block, 561 s dense;
  [the transport's build](docs/performance/transport_build.md); three artists' scenes
  opened from their files, 149 to 260 s, [load](docs/performance/load.md)), and until it lands `gi`,
  `gi_threads` and `gi_tile` draw it without the indirect light.
- **A plain glTF export loses part of an artist's scene** (materials, sky, framing or
  geometry, by scene): what it keeps and what it loses is in
  [glTF truth](docs/performance/gltf_truth.md).
- **The presets that read a scene's materials** (`textured`, `lit`, `gi` and their
  threads' forms) are refused on a generated scene.
- **A size past the capacity a load holds** is a reload of the program; a load that is
  refused stays at the size before. Lists too small for a camera grow in the live run.
- **The viewer's field of view** is 0.5 to 179 degrees.
- **Komorebi 0.6.0 or later.**

## Repository map

```text
src/prism_common/          registry and build, slots and their contract, formats, paths
src/prism_reference/       the algorithms in numpy: scene (generated, public, opened glTF),
                           raster, material, direct, indirect (field, hierarchical matrix),
                           post, trace (the box tree, the batch tracer), native, io
src/prism/
  core/                    the pipeline, an implementation and its host's contract, the
                           unit, a step and a kind (thread/), the thread's layout, shared
                           fields, capacity, controls; include/ (device headers shared)
  stages/                  raster; material/texture; direct/shadow_pcf, direct/light;
                           indirect/transport, indirect/field_update; post/show; each
                           with its steps/ (its step of the tile thread)
  program/                 the assembly: form (stage-wise or threads), threads/ (the threads'
                           presets' assembly, tile threads, hosts), dispatch/ (the view's
                           pulls on the frame's thread), frame/ (the handler work), jobs/
                           (the job thread), director/ (the thread's runtime in C)
  loop/                    a pipeline kept loaded: frames, sizes, recoveries, camera paths
  check/                   the harness: a preset's frames against prism_reference
apps/
  prism_cli/               the command line: run, open
  prism_viewer/            the viewer: server/ and web/ (Vue 3 + Vite)
configs/pipeline/          the presets
scripts/                   run/ (presets, stages, accounts), data/ (the scenes), blender/
checks/                    behaviour scripts run by hand; repo_rules.py
docs/                      concepts, guides, internals, performance; images/
measurements/              every recorded run, a README a folder
```

## Documentation

| Page | Read it for |
|---|---|
| [docs index](docs/README.md) | every page by kind |
| [quick start](docs/guides/quick_start.md) | from an installed Komorebi to a picture and the viewer |
| [the renderer](docs/concepts/renderer.md) | the pipeline, the slots between its parts, the presets |
| [the frame as threads](docs/concepts/threads.md) | the kinds, the tile thread and its steps, the pulls, what a core keeps, the views |
| [light transport](docs/concepts/light_transport.md) | elements, the transport matrix as blocks, its apply, the field and its update |
| [scenes](docs/concepts/scenes.md) | the public and generated scenes, their credits, materials, lighting and indirect light |
| [the command line](docs/guides/cli.md), [the viewer](docs/guides/viewer.md) | `run`, `open`, the preset runner; the server and the page |
| [glTF scenes](docs/guides/gltf_scenes.md), [artists' scenes](docs/guides/artist_scenes.md) | opening a glTF file; Blender scenes and the truth by Cycles |
| [dispatch](docs/internals/program/dispatch.md), [work](docs/internals/program/work.md), [steps](docs/internals/program/steps.md) | how the frame's thread and the handler `work` run a view |
| [gi_threads](docs/performance/gi_threads.md), [frames](docs/performance/frames.md), [account](docs/performance/account.md), [transport build](docs/performance/transport_build.md) | the renderer's frame and its update on ten scenes; the frame's time by preset, scene and size; where a threads' frame's time goes; the transport set's two builds on the host |
| [checks](docs/guides/checks.md), [scripts](scripts/README.md), [measurements](measurements/README.md) | what each check covers; every script; the records |

## Licence and credits

The code is under the Apache License 2.0 ([LICENSE](LICENSE)).

The repository holds no scene: the scenes are public ones, downloaded from their sources
by `scripts/data/public_scenes.py`, each under its own licence. The pictures in the docs
show Crytek Sponza (Frank Meinl, Crytek; CC BY 3.0), the Amazon Lumberyard Bistro
(Amazon Lumberyard, ORCA; CC BY 4.0) and the Breakfast Room (Wig42; CC BY 3.0), from
Morgan McGuire's Computer Graphics Archive, and The Modern Living Room (Wig42; CC BY 3.0),
from Benedikt Bitterli's Rendering Resources.
Every scene's source, credit and licence is in
[docs/concepts/scenes.md](docs/concepts/scenes.md#scenes-and-attribution).
