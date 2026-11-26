# Checks

Behaviour scripts, run by hand when the logic they cover changes. The checks of each
stage on the card against `prism_reference` are the presets' (`scripts/run/preset.py`,
`scripts/run/raster_frame.py`, `scripts/run/texture_frame.py`, `scripts/run/field.py`,
`scripts/run/apply.py`; [scripts](../scripts/README.md)).

| Script | Covers |
| --- | --- |
| `repo_rules.py` | import direction between packages, file length, ASCII source, in-function imports |
| `raster_model/` (`python -m checks.raster_model` from the repository's root; no card) | the raster stage's middle pass in C (`stages/raster/thread/`) built with host gcc and run on the model's counters of `tiny` and Sponza's overview (5, 120 and 240 fill cores), on seeded hot tiles and at 8,160 tiles, against `model.middle`; `setup.h`'s sizes built with g++ at ten capacities against `model.numbers.sizes`; the model's frame pages (`frame_of`, `decode_frame`) against the reference's plain frame of `tiny`, `s10k` and Sponza's overview; SETUP at the middle pass's slots against `build_lists` and the reference's binning; exit 1 on a difference; `$PRISM_DATA`, `$PRISM_BUILD` |
| `scene_description/` (`python -m checks.scene_description [--files <folder>] [--box <Box.glb>]`; no card) | the scene description and the glTF importer: round trips of a `.glb` and a `.gltf` the check writes under `$PRISM_CACHE` (every attribute, accessor component type and type, strided and normalized views, sparse accessors, the node tree, instancing, lights, cameras, every material field, the sidecar and the instance table), `flatten` against numpy, each refusal; with `--files`, each `.glb` of a folder loaded, checked and its counts (instanced nodes over the whole file) against `<name>.json`, with load seconds and peak memory; with `--box`, Khronos' Box; exit 1 on a difference ([scene description](../docs/concepts/scene_description.md)) |
| `apps/prism_viewer/server/check.py` (`python -m prism_viewer.server.check --pipeline lit --scene sponza --view overview`, on card 0 by default; `raster`, `textured`, `lit`) | the viewer's server without a browser: 403 without the token on every route, state and catalog, poses and their frames from the stream, two sizes (one a reload), refusals, each control the loop lists moved and moved back at the view's own pose, the stop by SIGTERM, then each frame's JPEG against the loop's picture through the same encoder (mean absolute difference at most 0.5; another pose must fail it) and the loop's picture by the preset's JUDGE (numbers reported); exit 1 on a failure (`docs/guides/viewer.md`) |
