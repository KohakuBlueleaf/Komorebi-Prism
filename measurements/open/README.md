# Opening a scene file: the account of a load

`python -m prism_cli open <file>` ([the command line](../../docs/guides/cli.md#open)) on
four scenes of the artists' table, each exported by the Blender workbench (`scene.glb`,
its sidecar and its instance table), at 1,920 x 1,080: where the seconds of one load go,
part by part, cold and warm, for the presets `textured` and `lit`, and the bake of the
sky's visibility alone.

- Card: one Blackhole P150A, card 1, a shared card (the wait for its lock is outside
  every time here: each time is measured inside the command).
- Host: AMD EPYC 7K62; the command ran on 8 of its CPUs. Date: 2026-11-26 (UTC+8),
  Komorebi at e908d6d16. Every frame's code 0; no load was refused.
- Each run: `python -m prism_cli open <folder>/scene.glb --pipeline P --size 1920 1080
  --card 1 --most-triangles 40000000 --out <folder>` (`--bake background` for `lit`),
  16 frames on the scene's view. (`--most-triangles 40000000` stood for "no count refused";
  the command now refuses no count when the option is left out, with the same output.)
- In order, for each scene: `textured` cold (the data root empty of that scene, the build
  caches empty: Komorebi's (`KMR_CACHE`) and tt-metal's (`TT_METAL_CACHE`), new for each
  scene, so its host module and the card's firmware are built too); the same command
  again, warm; `lit`, whose lights are made with every vertex's sky visibility 1 and whose
  bake starts as a process of its own; when that bake had ended, `lit` again (lights
  `baked`). The `lit` program is compiled at its first run (the caches held `textured`'s).
- The bakes started by the opens ran with 8 processes each (the command's CPUs), moved to
  32 other CPUs of the host after their start; the bakes of the three larger scenes
  overlapped there. `hidden_alley`'s bake was stopped at 2,400 s (40 minutes): it had
  built its tree and its 8 processes had traced for 2,334 s each, no visibility file
  written; the lights stayed `open`, and the open run after it is the row "lit, again
  after the bake was stopped".

## What is here

| file | holds |
| --- | --- |
| `<scene>_<run>.json` | the command's record (one JSON object): the scene's name and key, converted or found, the lights' state, the frames' codes, the seconds to the first picture, the account (`account.seconds`, `account.tensors`, `account.builds`, the peak memory) |
| `bake.json` | the bake alone: by scene and process count, the seconds, the rays and the rays a second |
| `first_lit/<scene>_<first|second>.json` | the records of [the first lit picture without the host's shadow map](#the-first-lit-picture-without-the-hosts-shadow-map) |
| `convert_memory.json` | the conversion alone: by scene, its seconds, its steps and the process's peak resident memory after it |
| `waste/` | the records of [the waste cut](#the-waste-cut): the host part's parts (`<scene>_host_<before|final>.json`), the card part's (`<scene>_card_<before|final>_<cold|warm>.json` and the command's `..._record.json`), the bake's samples (`bake_samples.json`) |

## The columns

Seconds, each part exclusive of the tensor writes inside it (they are their own column):

| column | what it is |
| --- | --- |
| digest | the BLAKE2b digest of the scene file, its sidecar and its instance table (the scene's key) |
| convert | the conversion, summed over its steps (`convert.<step>` in the record: `import`, `flatten`, `materials`, `textures`, `shared_vertices`, `uv`, `writing`, `entry`); 0 when the scene was found |
| lights | the lights with the sky's visibility 1, less the shadow map (the environment map, the sky's octahedral map, the lamps, the file) |
| shadow map | the sun's shadow map in those lights |
| module | Komorebi's host module imported (built first when its cache is empty) |
| read back | the mesh, the materials and (for `lit`) the lights read back from their files |
| session | the session's start: the card opened |
| host models | the tables the stages' hosts make from the scene (`prepare` and `connect`), summed; by implementation in the second table |
| program made | the assembly less its hosts: the classes made and merged, the thread's layout |
| program build | the program's builds (compiled, or found in the build's cache: `account.builds`) |
| program launch | the load less the builds and the binds: the kernels launched, the card opened again when the kernels ask for another kernel buffer, the thread started |
| tensors GB; s | the bytes and seconds of the tensors written to the card while the pipeline is opened; by implementation in the second table (`load`: outside every host's call, in the cold runs mostly the tensors made again when the card is opened again) |
| first frame | the first frame and its picture |
| 16 frames | all 16 frames, the first and the last with their pictures |
| other | the command's seconds less every part above |
| first picture | from the command's start to the first frame's picture (the process's start is 0.2 to 0.3 s earlier: `first_picture_seconds_from_process`) |
| command | the command's seconds, the PNG written |
| peak RSS GiB | the process's peak resident memory |

## The loads

Each scene: the parts of each run, then the host models and the tensors by implementation.

### classroom

| run | digest | convert | lights | shadow map | module | read back | session | host models | program made | program build | program launch | tensors GB; s | first frame | 16 frames | other | first picture | command | peak RSS GiB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| textured, cold | 0.03 | 2.38 | 0.00 | 0.00 | 17.07 | 0.07 | 3.56 | 1.13 | 3.55 | 5.97 | 8.47 | 1.36; 1.75 | 0.02 | 0.16 | 0.25 | 44.06 | 44.39 | 1.0 |
| textured, warm | 0.03 | 0.00 | 0.00 | 0.00 | 0.32 | 0.07 | 1.01 | 1.14 | 0.84 | 0.08 | 0.68 | 0.68; 0.21 | 0.02 | 0.16 | 0.24 | 4.48 | 4.80 | 1.0 |
| lit, lights open | 0.03 | 0.00 | 11.50 | 12.07 | 0.30 | 0.12 | 1.00 | 3.42 | 5.63 | 11.90 | 6.45 | 2.57; 1.78 | 0.03 | 0.30 | 0.25 | 54.29 | 54.75 | 2.0 |
| lit, lights baked | 0.03 | 0.00 | 0.00 | 0.00 | 0.34 | 0.15 | 1.14 | 3.03 | 1.34 | 0.10 | 0.85 | 1.28; 0.53 | 0.03 | 0.30 | 0.26 | 7.62 | 8.09 | 1.5 |

| run | model raster | model texture | model shadow_pcf | model light | model show | tensors by implementation, MB; s |
|---|---|---|---|---|---|---|
| textured, cold | 0.81 | 0.32 | - | - | 0.00 | raster 646; 1.53, material.texture 10; 0.01, post.show 9; 0.01, load 698; 0.20 |
| textured, warm | 0.81 | 0.32 | - | - | 0.00 | raster 646; 0.18, material.texture 10; 0.01, post.show 9; 0.01, load 18; 0.01 |
| lit, lights open | 2.48 | 0.69 | 0.06 | 0.18 | 0.01 | raster 1063; 0.29, material.texture 94; 0.24, direct.light 69; 0.04, post.show 9; 0.03, load 1333; 1.18 |
| lit, lights baked | 2.35 | 0.55 | 0.03 | 0.09 | 0.01 | raster 1063; 0.31, material.texture 94; 0.16, direct.light 69; 0.03, post.show 9; 0.01, load 51; 0.02 |

### italian_flat

| run | digest | convert | lights | shadow map | module | read back | session | host models | program made | program build | program launch | tensors GB; s | first frame | 16 frames | other | first picture | command | peak RSS GiB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| textured, cold | 0.82 | 22.18 | 0.00 | 0.00 | 17.01 | 0.68 | 3.69 | 6.96 | 3.56 | 5.92 | 8.54 | 5.92; 2.52 | 0.04 | 0.56 | 0.38 | 72.04 | 72.82 | 5.0 |
| textured, warm | 0.79 | 0.00 | 0.00 | 0.00 | 0.32 | 0.68 | 1.06 | 6.92 | 0.84 | 0.08 | 0.67 | 2.96; 0.59 | 0.04 | 0.56 | 0.33 | 12.06 | 12.84 | 4.5 |
| lit, lights open | 0.79 | 0.00 | 11.86 | 50.99 | 0.30 | 0.74 | 1.04 | 15.54 | 4.79 | 11.82 | 6.21 | 10.89; 3.59 | 0.05 | 0.63 | 0.40 | 107.79 | 108.71 | 6.0 |
| lit, lights baked | 0.83 | 0.00 | 0.00 | 0.00 | 0.34 | 0.82 | 1.05 | 17.13 | 1.21 | 0.10 | 0.85 | 5.44; 1.49 | 0.05 | 0.62 | 0.38 | 23.93 | 24.81 | 6.0 |

| run | model raster | model texture | model shadow_pcf | model light | model show | tensors by implementation, MB; s |
|---|---|---|---|---|---|---|
| textured, cold | 4.59 | 2.36 | - | - | 0.00 | raster 2610; 1.89, material.texture 319; 0.05, post.show 9; 0.01, load 2987; 0.57 |
| textured, warm | 4.54 | 2.38 | - | - | 0.00 | raster 2610; 0.52, material.texture 319; 0.05, post.show 9; 0.01, load 26; 0.01 |
| lit, lights open | 11.97 | 2.96 | 0.28 | 0.32 | 0.00 | raster 4788; 1.20, material.texture 487; 0.30, direct.light 69; 0.02, post.show 9; 0.01, load 5533; 2.06 |
| lit, lights baked | 13.13 | 3.39 | 0.28 | 0.33 | 0.00 | raster 4788; 1.09, material.texture 487; 0.33, direct.light 69; 0.02, post.show 9; 0.01, load 92; 0.03 |

### lynxsdesign

| run | digest | convert | lights | shadow map | module | read back | session | host models | program made | program build | program launch | tensors GB; s | first frame | 16 frames | other | first picture | command | peak RSS GiB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| textured, cold | 0.96 | 46.60 | 0.00 | 0.00 | 19.47 | 1.14 | 4.19 | 18.19 | 3.94 | 6.75 | 9.20 | 9.76; 3.54 | 0.06 | 0.72 | 0.63 | 114.16 | 115.33 | 9.3 |
| textured, warm | 0.93 | 0.00 | 0.00 | 0.00 | 0.33 | 1.14 | 1.01 | 17.84 | 0.92 | 0.10 | 0.75 | 4.88; 0.98 | 0.06 | 0.72 | 0.58 | 24.13 | 25.30 | 8.8 |
| lit, lights open | 0.93 | 0.00 | 6.99 | 94.56 | 0.29 | 1.19 | 1.02 | 38.13 | 4.04 | 8.31 | 6.86 | 11.86; 2.72 | 0.07 | 0.82 | 0.64 | 165.19 | 166.51 | 9.2 |
| lit, lights baked | 0.93 | 0.00 | 0.00 | 0.00 | 0.33 | 1.22 | 1.04 | 38.10 | 1.07 | 0.08 | 0.83 | 5.93; 1.44 | 0.07 | 0.81 | 0.55 | 45.18 | 46.40 | 9.2 |

| run | model raster | model texture | model shadow_pcf | model light | model show | tensors by implementation, MB; s |
|---|---|---|---|---|---|---|
| textured, cold | 11.78 | 6.41 | - | - | 0.00 | raster 4457; 2.47, material.texture 389; 0.07, post.show 9; 0.01, load 4904; 0.99 |
| textured, warm | 11.57 | 6.27 | - | - | 0.00 | raster 4457; 0.89, material.texture 389; 0.07, post.show 9; 0.01, load 26; 0.01 |
| lit, lights open | 29.03 | 8.13 | 0.46 | 0.51 | 0.00 | raster 5205; 1.00, material.texture 557; 0.33, direct.light 69; 0.02, post.show 9; 0.01, load 6021; 1.36 |
| lit, lights baked | 29.03 | 8.09 | 0.46 | 0.51 | 0.00 | raster 5205; 1.06, material.texture 557; 0.33, direct.light 69; 0.02, post.show 9; 0.01, load 92; 0.03 |

### hidden_alley

| run | digest | convert | lights | shadow map | module | read back | session | host models | program made | program build | program launch | tensors GB; s | first frame | 16 frames | other | first picture | command | peak RSS GiB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| textured, cold | 2.48 | 61.67 | 0.00 | 0.00 | 21.15 | 1.81 | 5.22 | 19.66 | 4.03 | 7.22 | 9.73 | 12.73; 4.33 | 0.07 | 0.89 | 0.53 | 137.57 | 138.70 | 10.4 |
| textured, warm | 2.46 | 0.00 | 0.00 | 0.00 | 0.34 | 1.88 | 1.14 | 20.47 | 1.08 | 0.11 | 0.81 | 6.37; 1.41 | 0.07 | 0.89 | 0.39 | 29.84 | 30.98 | 9.7 |
| lit, lights open | 2.47 | 0.00 | 14.13 | 98.89 | 0.31 | 1.89 | 1.04 | 32.64 | 4.03 | 7.62 | 4.59 | 13.38; 3.27 | 0.08 | 0.95 | 0.37 | 171.05 | 172.22 | 9.9 |
| lit, again after the bake was stopped (lights open) | 2.37 | 0.00 | 0.00 | 0.00 | 0.33 | 1.79 | 1.03 | 29.16 | 1.06 | 0.09 | 0.85 | 6.69; 1.51 | 0.08 | 0.95 | 0.37 | 38.33 | 39.51 | 9.9 |

| run | model raster | model texture | model shadow_pcf | model light | model show | tensors by implementation, MB; s |
|---|---|---|---|---|---|---|
| textured, cold | 12.09 | 7.56 | - | - | 0.01 | raster 5142; 2.70, material.texture 1188; 0.20, post.show 9; 0.01, load 6389; 1.42 |
| textured, warm | 12.51 | 7.95 | - | - | 0.00 | raster 5142; 1.16, material.texture 1188; 0.22, post.show 9; 0.01, load 26; 0.02 |
| lit, lights open | 21.67 | 9.94 | 0.49 | 0.53 | 0.00 | raster 5165; 1.20, material.texture 1357; 0.53, direct.light 69; 0.02, post.show 9; 0.01, load 6780; 1.51 |
| lit, again after the bake was stopped (lights open) | 19.48 | 8.64 | 0.49 | 0.53 | 0.00 | raster 5165; 1.01, material.texture 1357; 0.44, direct.light 69; 0.03, post.show 9; 0.01, load 92; 0.03 |

## Seconds to the first picture

| scene | triangles drawn | textured, cold | textured, warm | lit, lights open | lit, lights baked |
|---|---|---|---|---|---|
| classroom | 607,484 | 44.1 | 4.5 | 54.3 | 7.6 |
| italian_flat | 3,358,422 | 72.0 | 12.1 | 107.8 | 23.9 |
| lynxsdesign | 8,806,420 | 114.2 | 24.1 | 165.2 | 45.2 |
| hidden_alley | 8,994,024 | 137.6 | 29.8 | 171.0 | bake stopped; again, lights open: 38.3 |

## The largest three parts of each warm load

Seconds, the tensor writes counted as one part.

- classroom: textured: `session.start` 1.0, `program.made` 0.8, `model.raster` 0.8; lit, baked: `model.raster` 2.4, `program.made` 1.3, `session.start` 1.1.
- italian_flat: textured: `model.raster` 4.5, `model.material.texture` 2.4, `session.start` 1.1; lit, baked: `model.raster` 13.1, `model.material.texture` 3.4, `tensors` 1.5.
- lynxsdesign: textured: `model.raster` 11.6, `model.material.texture` 6.3, `session.start` 1.0; lit, baked: `model.raster` 29.0, `model.material.texture` 8.1, `tensors` 1.4.
- hidden_alley: textured: `model.raster` 12.5, `model.material.texture` 8.0, `digest` 2.5; lit, open, warm: `model.raster` 19.5, `model.material.texture` 8.6, `digest` 2.4.

## The hosts' tables made once

The same command after the raster host stopped running the reference's whole setup to
size its lists (the counts now come from the pieces' boxes alone: `setup.boxes`,
`fill.tile_counts`), and after each layer's mesh and shade blocks were made once for the
two hosts and kept under `$PRISM_CACHE/blocks/` ([the raster model](../../docs/internals/raster/model.md#the-lists-slots-a-load-holds)).
Date 2026-11-26, card 1, the same 8 CPUs, Komorebi at e908d6d16, `--bake none`, 16 frames
on the scene's view; the lights as above (`hidden_alley`'s `open`). For each scene and
preset: one open to fill the build caches, the blocks' cache emptied, then three opens in
a row: the first makes and keeps the blocks, the second and third find them. Every
frame's code 0; every PNG equal byte for byte to the one of the warm run above
(`hidden_alley`, `lit`: of the run after the bake was stopped). `tables/` holds the first
and the second's records (`<scene>_<preset>_<first|kept>.json`); the third's were within
0.25 s of the second's.

Seconds: to the first picture, `model.raster`, `model.material.texture`; before: the warm
records above (`lit`: lights baked; `hidden_alley`: again after the bake was stopped).

| scene | preset | before | first | kept |
|---|---|---|---|---|
| classroom | textured | 4.5; 0.81; 0.32 | 4.0; 0.64; 0.06 | 3.6; 0.27; 0.06 |
| classroom | lit | 7.6; 2.35; 0.55 | 5.3; 1.35; 0.07 | 4.9; 0.88; 0.08 |
| italian_flat | textured | 12.1; 4.54; 2.38 | 9.7; 4.07; 0.62 | 7.2; 1.53; 0.62 |
| italian_flat | lit | 23.9; 13.13; 3.39 | 15.5; 8.25; 0.66 | 12.3; 5.10; 0.67 |
| lynxsdesign | textured | 24.1; 11.57; 6.27 | 17.1; 10.14; 1.10 | 10.5; 3.44; 1.10 |
| lynxsdesign | lit | 45.2; 29.03; 8.09 | 29.4; 20.63; 1.27 | 21.3; 12.40; 1.29 |
| hidden_alley | textured | 29.8; 12.51; 7.95 | 19.8; 9.96; 1.63 | 13.0; 3.15; 1.63 |
| hidden_alley | lit | 38.3; 19.48; 8.64 | 26.9; 15.54; 1.72 | 18.9; 7.40; 1.78 |

The blocks' cache a scene and preset (`textured` and `lit` keep one folder each, of the
same size):

| scene | bytes |
|---|---|
| classroom | 53,459,399 |
| italian_flat | 335,844,075 |
| lynxsdesign | 880,644,051 |
| hidden_alley | 899,408,323 |

## The first lit picture without the host's shadow map

The same command after two changes: `open` makes the lights with `shadow="card"` (the
sun's map is not rendered on the host: the lighting file holds its camera, texel and side
and a 1 x 1 placeholder, and the preset's SUN command draws the map on the card before
the first frame is lit, [the lights' shadow](../../docs/concepts/scenes.md#lighting)), and
the raster host's lists' counts are kept under `$PRISM_CACHE/counts/` ([the raster
model](../../docs/internals/raster/model.md#the-lists-slots-a-load-holds)). Date
2026-11-26, card 1, the same 8 CPUs, Komorebi at e908d6d16, `--pipeline lit --bake none`,
16 frames on the scene's view. For each scene: its lighting file removed from the data
root (its visibility file kept: `classroom`, `italian_flat`, `lynxsdesign`; none for
`hidden_alley`, whose lights stay `open`), the blocks' and counts' caches empty, then
three opens in a row: the first makes the lights, the blocks and the counts; the second
and third find them. Komorebi's and tt-metal's build caches were new and empty before
`classroom`'s first open (its `module` 17.1 s, `program.build` 8.1 s, `session.start`
3.6 s); the later scenes' first opens found the module and built only their program (7.4
to 7.5 s). Every frame's code 0; every PNG equal byte for byte to the picture of the runs
above (`lit`, lights baked; `hidden_alley`: the run after the bake was stopped).
`first_lit/` holds the first and the second's records (`<scene>_<first|second>.json`); the
third's first picture was within 0.2 s of the second's.

Seconds: to the first picture; `lights.open`; `lights.open.shadow_map` (now the map's
camera and texel alone); `model.raster`. Before: the first lit open above (`lit, lights
open`) and the warm one of the hosts' tables made once (`tables/<scene>_lit_kept.json`).

| scene | first lit open before | first | warm before | second |
|---|---|---|---|---|
| classroom | 54.29; 11.50; 12.07; 2.48 | 57.08; 11.47; 0.06; 1.47 | 4.89; 0.00; 0.00; 0.88 | 4.16; 0.00; 0.00; 0.16 |
| italian_flat | 107.79; 11.86; 50.99; 11.97 | 42.99; 12.15; 0.56; 9.00 | 12.34; 0.00; 0.00; 5.10 | 8.66; 0.00; 0.00; 1.25 |
| lynxsdesign | 165.19; 6.99; 94.56; 29.03 | 53.05; 7.22; 0.92; 22.05 | 21.29; 0.00; 0.00; 12.40 | 11.43; 0.00; 0.00; 2.54 |
| hidden_alley | 171.05; 14.13; 98.89; 21.67 | 56.84; 13.67; 0.99; 16.81 | 18.91; 0.00; 0.00; 7.40 | 13.76; 0.00; 0.00; 2.32 |

## The bake alone

`python scripts/data/public_scenes.py lighting <name> --rebake --workers N` on 32 CPUs of
the host, nothing else running on them; 64 rays a vertex. The bakes the opens started are
below them (8 processes; `italian_flat`'s overlapped `lynxsdesign`'s and `hidden_alley`'s;
`lynxsdesign`'s was moved to 8 other CPUs after 1,150 s).

| scene | vertices | how | processes | seconds | rays | rays a second |
|---|---|---|---|---|---|---|
| classroom | 468,446 | alone | 8 | 97.3 | 29,980,544 | 308,039 |
| classroom | 468,446 | alone | 32 | 39.0 | 29,980,544 | 767,788 |
| italian_flat | 4,664,706 | alone | 8 | 1,586.9 | 298,541,184 | 188,130 |
| italian_flat | 4,664,706 | alone | 32 | 572.4 | 298,541,184 | 521,522 |
| classroom | 468,446 | started by open | 8 | 105.6 | 29,980,544 | 283,872 |
| italian_flat | 4,664,706 | started by open | 8 | 1,843.9 | 298,541,184 | 161,908 |
| lynxsdesign | 7,679,078 | started by open | 8 | 2,250.5 | 491,460,992 | 218,382 |

## The conversion's memory

`open_scene` alone (the call `open` makes) in a fresh process on an empty data root, no
card, on the same 8 CPUs: the conversion's seconds and the process's peak resident memory
right after it (`peak_rss_convert_mib`, which the command's record now carries too). The
names are the same as in the loads above.

| scene | triangles | seconds | peak RSS after the conversion, GiB |
|---|---|---|---|
| classroom | 607,484 | 2.3 | 0.35 |
| italian_flat | 3,358,422 | 23.2 | 4.76 |
| lynxsdesign | 8,806,420 | 46.0 | 5.09 |
| hidden_alley | 8,994,024 | 58.5 | 6.75 |

## The waste cut

The load the frame `gi` needs (its scene's conversion, its lights, its hosts' tables, its
program, its tensors), before and after cutting the work nobody needed, on the new
exports of three scenes: classroom (1,252,126 triangles), lynxsdesign (29,756,735),
hidden_alley (8,994,697). A scene without a transport set opens as `gi` without its
indirect term, the implementations of `lit`; the rows below are named by part. Date
2026-11-27 (UTC+8), card 1, 24 CPUs of the host (every command under the same 24), Komorebi
0.6.0. Each scene: the host part in a process of its own, no card (`open_scene`, then the
lights with `visibility="open"` and `shadow="card"`, the calls `open` makes), the data
root empty of that scene; then `python -m prism_cli open <folder>/scene.glb --pipeline lit
--bake none --size 1920 1080 --card 1`, 16 frames, cold (Komorebi's, tt-metal's and the
cache root's folders emptied) and warm. The kind of each part's time is from `py-spy
--native` samples: numpy's compiled loops, other native code (Pillow and zlib, BLAKE2b,
the compiled tracer) or the interpreter; the interpreter's share was under 5 % of each
part's samples but the HDR map's reading (about a third) and the texture decoding (6 to
12 %, Pillow's Python around its decoders).

Every file the conversion writes (the mesh, the materials) is equal byte for byte before
and after on the three scenes; the lighting files differ in one timed number of their
`counts`; every PNG (cold and warm) is equal byte for byte; the baked visibility of
classroom by the compiled tracer equals the whole bake by the numpy tracer byte for byte,
and on the two larger scenes 24 runs of 16,384 vertices each (25,165,824 rays) are equal.
The caches' keys of the hosts' tables (`blocks/`, `counts/`) are another digest now
(`prism_common.digest`, version 2): a cache of the earlier form is made again once.

Seconds by part, lynxsdesign | hidden_alley | classroom.

| part | before | after | kind | what was cut |
|---|---|---|---|---|
| convert.textures | 11.9 / 27.2 / 7.9 | 4.3 / 9.0 / 2.4 | layout, compute split | the mip's 2 x 2 box filter as four strided adds (a reduce over two small strided axes before, 11 x slower); the decoders on every CPU given (4 before) |
| convert.shared_vertices | 140.7 / 32.2 / 4.3 | 10.0 / 3.0 / 0.35 | algorithm | a sort of every corner's 4-column row replaced by integer keys: a colour ranked once, one pair a vertex of one colour, only the vertices between colours sorted |
| convert.uv | 10.8 / 7.2 / 0.5 | 5.9 / 1.4 / 0.15 | needless | a full scan of every triangle per material replaced by one stable sort |
| convert, all steps and the digest | 174.8 / 75.2 / 14.1 | 33.7 / 21.9 / 4.2 | | |
| lights.open | 10.3 / 13.9 / 11.9 | 9.3 / 8.6 / 7.3 | twice, needless | the HDR map read and its environment made once (twice with an authored sun); the materials (1.4 GB) not read when the lamps are authored and the shadow is the card's |
| host part, peak memory GiB | 15.8 / 7.2 / 2.7 | 13.7 / 8.2 / 3.1 | | |
| model.raster, cold | 112.4 / 18.6 / 3.3 | 21.5 / 8.2 / 1.6 | needless, split | `setup.boxes` without the clip's recipes it never reads, on every CPU by runs of triangles; the mesh blocks by runs of whole blocks on every CPU and as a reshape; the keys' digests on every CPU |
| model.material.texture, cold | 5.6 / 2.0 / 0.44 | 1.0 / 0.86 / 0.34 | twice | the same blocks' digest (made by the raster host first) on every CPU |
| model.raster, warm | 7.7 / 3.2 / 0.45 | 0.70 / 0.67 / 0.30 | layout | the keys' digests (BLAKE2b over 0.6 to 2 GB a call, eight calls a load) on every CPU |
| model.material.texture, warm | 3.6 / 1.9 / 0.41 | 0.94 / 0.93 / 0.30 | layout | as above |
| card part, peak memory GiB, cold | 15.6 / 5.0 / 1.9 | 14.7 / 8.0 / 2.3 | | the blocks and boxes made by runs at once |

Seconds to the first picture: the host part plus the card part's command to its first
picture (the card part's process start is 0.2 to 0.3 s more).

| scene | cold before | cold after | warm before | warm after |
|---|---|---|---|---|
| lynxsdesign | 185.0 + 187.0 = 372.0 | 43.0 + 90.7 = 133.7 | 31.2 | 21.3 |
| hidden_alley | 89.1 + 81.8 = 170.9 | 30.5 + 73.6 = 104.1 | 19.8 | 16.2 |
| classroom | 26.1 + 55.5 = 81.6 | 11.5 + 50.9 = 62.4 | 7.6 | 7.1 |

What is left, cold (lynxsdesign): Komorebi's host module built 17.1 (one compiler, one
CPU), the program built 8.2 and launched 9.2, with the card opened again when the kernels
ask for a larger kernel buffer and every tensor written again (11.1 GB in 7.5 s, cold
only); the tensors 22.1 GB in 16.4 s (the card's PCIe link was found at 2.5 GT/s later
the same day, 16 GT/s being its normal speed; the link's speed during these runs was
not recorded, so the tensors' seconds are an upper bound); the digest of the files 2.7 (BLAKE2b, one CPU, every
open, warm too: the scene's key is the digest of the bytes); the conversion's writing 5.5
(2.3 GB); the HDR map's run-length rows 4 (the interpreter: a serial format); `sun_view`
2.8. The mesh's colours and the materials' `light` (`vertex_shade`) are not read by `gi`
(its blocks carry u, v and the visibility), only by `textured` and the public scenes;
they cost about 6 s of the conversion.

### The sky's visibility bake

`python scripts/data/public_scenes.py lighting NAME --visibility bake --shadow card
--rebake --workers 24`, the command `open --bake background` starts. Before, each process
traced its rays with the reference's numpy tracer (`trace.tracer`: one walk over the tree
in vectorized steps a chunk of 65,536 rays); after, the compiled batch tracer
(`trace.batch`, the same walk and triangle test in float32 without fused multiply-add)
traces 16,384 vertices (1,048,576 rays) a thread on every CPU, and the median tree's
lexicographic sort of each level is one stable sort of a 64-bit key, by runs of whole
segments on every CPU (the tree equal array for array).

| scene | vertices | rays | before: rays a second | before, seconds | after: tree and files, seconds | after: bake, seconds | after: rays a second |
|---|---|---|---|---|---|---|---|
| classroom | 963,928 | 61,691,392 | 598,898 (the whole bake) | 103.0 + 8.4 tree | 11.1 | 7.3 | 8,429,000 |
| hidden_alley | 9,115,111 | 583,367,104 | 248,097 (a 25 M ray sample) | about 2,350 + 50 tree | 36.0 | 78.0 | 7,478,000 |
| lynxsdesign | 19,745,143 | 1,263,689,152 | 313,904 (a 25 M ray sample) | about 4,030 + 184 tree | 84.9 | 125.4 | 10,078,000 |

An on-card form of this bake would need: the tree resident in the card's memory
(lynxsdesign: 59.5 M nodes of 32 B and 29.8 M triangles of 36 B, 3.0 GB) or cut into
treelets an L1 holds (`trace.tree.cut_treelets`); each vertex's position and normal (24 B,
0.47 GB) and its visibility out (4 B); the rays made on the card from the vertex's hash
(`bake_directions`), none sent; an any-hit walk with a stack of 64 entries a ray on the
cores, the box and triangle tests in float32 in the reference's order without fused
multiply-add to stay equal to the host; the vertices handed out to the cores in runs as
they finish, since a run's cost follows the scene.
