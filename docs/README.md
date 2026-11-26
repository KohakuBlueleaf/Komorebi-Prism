# Docs

- `concepts/`: what the parts are and how they fit.
- `guides/`: how to use them: the command line, the viewer, scenes, the checks.
- `internals/`: how a thing works and why it is this way.
- `performance/`: measured numbers and what they say.

The numbers on every page come from the records' pages under
[measurements](../measurements/README.md). The README's figures (`images/teaser-*.svg`,
`images/frame-*.svg`) are drawn by `python docs/images/pipeline.py`, which needs only the
standard library; its docstring names the code and the records each figure is taken from.

## Concepts

| page | what it says |
|---|---|
| [concepts/renderer.md](concepts/renderer.md) | the pipeline (visibility, materials, direct light and the sun's shadow, indirect light, display), the slots between its parts, the presets and their forms |
| [concepts/threads.md](concepts/threads.md) | the frame as threads: the four phases of a view, the kinds, the tile thread and its steps, the pulls and who hands out what, what a core keeps, the frame's thread, the views, lists too small |
| [concepts/light_transport.md](concepts/light_transport.md) | elements, the transport matrix as blocks, its apply on the card, the field, its update in each preset, what moves the sun |
| [concepts/scenes.md](concepts/scenes.md) | the generated and public scenes, their credits, conversion, materials, lighting and indirect light |
| [concepts/scene_description.md](concepts/scene_description.md) | the scene description, the glTF importer, its sidecar and its check |

## Guides

| page | what it says |
|---|---|
| [guides/quick_start.md](guides/quick_start.md) | from an installed Komorebi to a picture and the viewer |
| [guides/environment.md](guides/environment.md) | the environment variables the code reads, and Komorebi's that a run on a card reads |
| [guides/cli.md](guides/cli.md) | the presets, the command line (`run`, `open`) and the preset runner |
| [guides/viewer.md](guides/viewer.md) | the viewer: its server, its page, the scene menu, its notices |
| [guides/gltf_scenes.md](guides/gltf_scenes.md) | opening a glTF file: the command, the material mapping, the view, the lighting |
| [guides/artist_scenes.md](guides/artist_scenes.md) | the artists' Blender scenes: the workbench, the plain export, the truth by Cycles reading the same glTF |
| [guides/checks.md](guides/checks.md) | what `checks/` and each stage's check do |

## Internals

| page | what it says |
|---|---|
| [internals/program/dispatch.md](internals/program/dispatch.md) | the dispatcher on the frame's thread: the phases, ranges and slices, the tile pull's choice, the need page |
| [internals/program/work.md](internals/program/work.md) | the handler `work`: the movers and the compute CPUs, a thread's life on a core |
| [internals/program/steps.md](internals/program/steps.md) | the contract of a step, a kind and a tile thread; how a stage gives one |
| [internals/program/director.md](internals/program/director.md) | the stage-wise form's frame thread |
| [internals/raster/model.md](internals/raster/model.md) | the raster stage's data on the host: records, lists, costs, heavy tiles, capacity |
| [internals/material/texture_model.md](internals/material/texture_model.md) | the texture stage's data: shade blocks, texture pages, SHADE's table, layers |
| [internals/direct/light_model.md](internals/direct/light_model.md) | the direct light's data: surface planes, terms, light pages, LIGHT's table, the sun, the field as LIGHT reads it |
| [internals/post/show.md](internals/post/show.md) | the display's conversion on the card |
| [internals/reference/raster.md](internals/reference/raster.md) | the reference's raster: setup, fill and SHADE |
| [internals/reference/material.md](internals/reference/material.md) | the reference's texture sampling and accesses |
| [internals/reference/direct.md](internals/reference/direct.md) | the reference's lit frame, its lights and glass |
| [internals/reference/indirect.md](internals/reference/indirect.md) | the reference's indirect light: elements, the hierarchical matrix, the sky, the field, against a traced truth |
| [internals/reference/surface.md](internals/reference/surface.md) | the metallic-roughness model, tangents, the texture filters, the surface planes and their comparison with Cycles |
| [internals/reference/described_light.md](internals/reference/described_light.md) | the direct light of a described scene, in units, against Cycles' passes |
| [internals/reference/trace.md](internals/reference/trace.md) | the box tree, the walk and the batch tracer |
| [internals/reference/transport_build.md](internals/reference/transport_build.md) | the transport built block by block: the pairs by block slices, mirrored pairs once, a far block's randomized range |

## Performance

| page | what it says |
|---|---|
| [performance/frames.md](performance/frames.md) | the frame's time on the card by preset, scene and size, in both forms |
| [performance/account.md](performance/account.md) | where a threads' frame's time and bytes go: the ways of handing out, a core's waits, the CPUs by step, the X280's choice |
| [performance/load.md](performance/load.md) | opening a glTF file: a load part by part, cold and warm |
| [performance/gltf_truth.md](performance/gltf_truth.md) | the artists' scenes through glTF: Cycles on the same file against the reference and the card |
