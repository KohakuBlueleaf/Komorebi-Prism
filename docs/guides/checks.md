# Checks

There is no test suite. A check is a behaviour script run by hand when the logic it covers
changes: the card's work against `prism_reference` (the algorithms in numpy, by the same
stage names), the threads' form against the stage-wise form, and the host's parts on
their own. The table of every script with its options is
[checks/README.md](../../checks/README.md); this page says which check goes with which
part and what each judges. Each prints one JSON line and exits 1 on a difference, unless
the table says it only reports.

## Without a card

| check | judges |
| --- | --- |
| `python checks/repo_rules.py` | the import direction between the packages, file length, ASCII source, imports inside functions |
| `python -m checks.raster_model` | the raster's middle pass in C, built with the host's compiler, against the raster model on `tiny` and Sponza's overview; `setup.h`'s sizes at ten capacities; the model's frame pages against the reference's plain frame; the list counts (`setup.boxes`, `fill.tile_counts`) against the reference's binning, and the counts kept under the cache root read back equal (`$PRISM_DATA`, `$PRISM_BUILD`) |
| `python -m checks.dispatch` | the tile pull's choice (`src/prism/program/dispatch/c/dispatch_choose.c`), built with the host's compiler and asked by a model of cores with random costs: under each way of handing out, every record handed exactly once, no core refused while a record is left, a kept slice only to its own core |
| `python -m checks.thread_model` | the tile threads' layout in numpy (`stages/raster/model/threads.py`: slices, items, bands, positions, places) against the reference's binning, on `tiny`, `s10k` in three layers and Sponza's overview at 1,920 x 1,080, also under a random order of 120 cores |
| `python -m checks.frame_build <module:NAME>` | the handler `work` (`src/prism/program/frame/`) composed from a tile thread and kinds given by dotted path, its class made and its kernels built for the five CPUs of a core by Komorebi's mock build; `toy:TOY` and `toy:WALK` are the check's own threads, which build the loop without any stage's step |
| `python -m checks.threads_frame model` | the threads checks' own parts against the model |
| `python -m checks.scene_description [--files DIR] [--box Box.glb]` | the scene description and the glTF importer: round trips of a `.glb` and a `.gltf` the check writes, `flatten` against numpy, each refusal; every `.glb` of a folder against its counts; Khronos' Box ([scene description](../concepts/scene_description.md)) |
| `python -m checks.gltf_scene` | the conversion of a glTF file into a scene of the tables: each row of the material mapping, a textured quad's texels where glTF puts them, the files read back, the view against the file's camera, `open_scene` found the second time and renamed by a changed sidecar, the lights `open`, with the card's shadow, then baked, each layer's blocks kept and read back equal ([glTF scenes](gltf_scenes.md)) |
| `python -m checks.artist_export DIR` | a scene written by the Blender workbench against its `stats.json`: the instance table's nodes, the drawn and stored triangles with the recorded drops added back, the area lights, the render camera, the sidecar's version ([artists' scenes](artist_scenes.md)) |
| `python -m checks.described_light` | the reference's direct light of a described scene, each light kind against its closed form ([described light](../internals/reference/described_light.md)) |
| `python -m checks.transport_build [--scene sponza] [--elements 6000]` | the transport built block by block (`prism_reference.indirect.blockwise`) against the dense build's blocks of the same elements: `y = M x` for a random `x` and the admissible blocks' relative Frobenius error, each at most 10 % above the dense build's; the `presorted` and `median` trees' any-hit results on 200,000 random segments equal (`$PRISM_DATA`; [the transport's build](../internals/reference/transport_build.md)) |
| `python -m checks.near_field` | the reference's near field of the indirect light on a box standing on a floor: the white furnace with the fusion on, the contact darker than the field alone ([near field](../internals/reference/near_field.md)) |
| `python -m checks.surface` | the reference's surface: the model's reciprocity and white furnace, the texture filters and wrap modes, the tangents, every plane of a normal-mapped quad ([surface](../internals/reference/surface.md)) |

`checks.raster_model` reads `$PRISM_DATA` and `$PRISM_BUILD`, `checks.thread_model` and
`checks.frame_build` `$PRISM_DATA`; the checks that write scenes put them in a new folder
under the cache root ([environment](environment.md)).

## Each stage on the card

Every implementation names a check (`Implementation.check`). The preset runner opens a
stage-wise preset and runs its last implementation's check through the harness, or the
function `--check` names ([the preset runner](cli.md#the-preset-runner)):

```
python scripts/run/preset.py --pipeline lit --scene sponza --view overview --size 1024 1024
```

| implementation | its check | judges |
| --- | --- | --- |
| `raster` | `prism.stages.raster.check.thread_frame` | the preset `raster`'s frames: the first, second and last pictures against the reference's vertex-colour frame, pixel for pixel |
| `material.texture` | `prism.stages.material.texture.check.thread_frame` | the first and last pictures against the reference's shaded frame |
| `direct.shadow_pcf` | `prism.stages.direct.shadow_pcf.check.sun_map` | the sun set, the card's shadow map against the reference's at that sun |
| `direct.shadow_pcf` (`--check`) | `prism.stages.direct.shadow_pcf.check.lamp_maps.check` | frames until every lamp face is drawn (LAMPS before them; a scene with lamp shapes, `--option file_lights=True`), each face's map against `lamp_maps.face_map` at every texel and its levels (exact), the faces' times |
| `direct.light` | `prism.stages.direct.light.check.thread_frame` | the first and last pictures against the reference's lit frame at the loop's sun, tone and terms, the sun's map when its pass ran |
| `indirect.transport` | `prism.stages.indirect.transport.check` | one apply against the emulation and the set's float result, then the run's applies timed (the preset `apply`) |
| `indirect.field_update` | `prism.stages.indirect.field_update.check` | the field's texels, sky and L0 after the updates against the reference's, whole or stepped (the preset `field`) |
| `post.show` | `prism.stages.post.show.check` | the pictures pushed and the display read back against the frame's own colour converted on the host (bit for bit) and against the reference of the stage before it |

Every display preset ends in `post.show`, so its check is the default one. The frames
with the field's update are checked by `--check prism.check.field_frames.check` (each sun
of the options in turn, the field the card wrote against the reference's, the pictures
after the update, the frames drawn during it), in both forms: the stage-wise update's
times row is the field update's thread region, the threads' form's the job thread's
region. In the threads' form a row also holds the update's span on the card (`span`,
ms at the thread's 50 MHz timer): from the start of the sources step to the end of the
finish step, every pass and the transport's applies the graph queues between them
included; the scale command and the `job_wants` that hands the field to the frame's
thread, both after the finish, are left out. The runs with their own scripts
(`scripts/run/raster_frame.py`, `texture_frame.py`, `field.py`, `apply.py`) step one part
by the host against the reference ([scripts](../../scripts/README.md)).

The record of a check (`prism.check.harness`): `check` (the function), `pipeline`,
`numbers` (what the check returns), `seconds`, `card`, `aiclk_mhz` (the card's clock
before and after), `pcie_link` (the card's PCI address and its link speed now and at
most, before and after) and `date`; written to `measurements/<preset>_frame/` by default. The
pages under `docs/performance/` quote the README tables made from such records.

## The threads' form against the stage-wise form

```
python -m checks.threads_frame model|tile|depth|geometry|whole|update|during \
    --pipeline <stage-wise preset> --scene S [--view V] [--size W H] [--cores 16 all] \
    [--policy ...] --card C
```

Each part runs the threads' preset `<pipeline>_threads` and the stage-wise preset on the
same scene and camera, at each count of cores and each way of handing out:

| part | compares |
| --- | --- |
| `tile` | the tile pull alone on the model's records, slices and lists: the picture byte for byte |
| `depth` | the sun's view alone as a DEPTH view (a map of one quadrant: `--shadow-side`, `--sun`): the map's pages byte for byte |
| `geometry` | the count pull, the sums and the place pull: their records, slices, positions and lists against the model |
| `whole` | the whole frame's picture (with lights: the sun set and its command sent, its map too); where it differs, the first differing tile, its record and the core that ran it |
| `update` | the field's update as the kept graph: the field's pages it writes against the stage-wise update's, word for word, then the frames after it |
| `during` | frames sent while the update runs: each equal to the stage-wise picture before the update or after it, never a mix |

On a code or a hang it prints where the frame stood: the frame thread's mark, each core's
gave-up word by name, the view's times. The record goes to
`measurements/threads_frame/<part>_<scene>[_<view>]_<W>_<H>.json` by default. The
threads' implementations name `prism.check.threads.whole.check` as their check: it takes
both presets, so the preset runner does not run it.

## A preset moved and served

| check | judges |
| --- | --- |
| `python -m checks.camera_moves --pipeline P [--against Q] --scene S --view V --card C` | a preset loaded once and moved out of the load's view by the viewer's pose math (turns, looks up and down to 80 degrees, walks): each frame's code, its reloads, its live recoveries (what grew, milliseconds), whether a field's update ran beside it (`--sun FRAME AZIMUTH ELEVATION`); with `--against`, each picture against the stage-wise preset's of the same camera byte for byte; exit 1 on a reload, a code or a differing picture; the record under the cache root's `camera_moves/` |
| `python -m prism_viewer.server.check --pipeline P --scene S --view V` | the viewer's server without a browser: the token, the state and catalog, poses and their frames, two sizes, refusals, each control moved and back, the field of view, the stop; each served JPEG against the loop's picture, and the loop's picture by the preset's `JUDGE` ([the viewer](viewer.md#checking-it)) |

`python -m prism_cli run ... --check FRAME ...` checks the frames it is given against the
preset's `REFERENCE` and `JUDGE` the same way, reporting the numbers without judging them
([the command line](cli.md#run)).
