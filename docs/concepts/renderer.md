# The renderer

A glTF file in, a frame out. A frame draws the scene's layers, gives each pixel its
material, lights it with the sun (through its shadow map), the lamps, the sky and, in the
`gi` presets, the indirect field, and converts it for display, all on the card. In the
threads' presets every step of a tile runs on the core that took the tile's thread
([the frame as threads](threads.md)); the stage-wise presets run the same parts as
commands on every core one after another, and draw the pictures the threads' presets are
compared with.

## The pipeline

A pipeline is a list of implementations in order (`prism.core.pipeline.Pipeline`). Each
fills an item of the pipeline (`raster`, `material`, `direct`, `indirect`, `post`) or
none, and names the slots it reads and writes. The renderer's parts:

| part | item | what it computes | stage-wise implementation | threads' implementation (what the tile thread runs) |
|---|---|---|---|---|
| visibility of the layers | `raster` | each layer's triangles counted into tiles, placed into lists, and filled: each pixel's 1/z, colour and triangle number, equal depths going to the lower triangle number | `raster` (passes COUNT to FILL a layer, a middle pass on the X280) | `raster.threads`: the count and place pulls, the sums, the step `visibility` |
| materials | `material` | each pixel's material colour (a textured material's albedo texel), the masked layer cut where its alpha is under 128 and merged, the glass layer blended over; with lights, each layer's surface (material word, normal, specular, albedo) | `material.texture` (SHADE a layer) | `material.texture.threads`: the step `material` or `material_lit` |
| the sun's shadow | none | the sun's shadow map, drawn as DEPTH views of the sun when it moves | `direct.shadow_pcf` (the thread command `sun`, no frame work) | the same; its views are the dispatcher's pulls, the steps `visibility`, `material_lit`, `depth_out` |
| direct light | `direct` | the sun with its shadow map's filter (PCF), the lamps, the specular terms, the sky, the ambient or the indirect field, emissive and the background, then the tone step; a scene with glass lit twice, the glass layer over the linear colour | `direct.light` (LIGHT a view) | `direct.light.threads`, or `direct.light.threads_field` with the field: the step `light` |
| indirect light | `indirect` | one apply of the scene's light-transport matrix, and the field made again from it after the sun moves ([light transport](light_transport.md)) | `indirect.transport`, `indirect.field_update` (the thread command `update`) | `indirect.transport.threads` (its apply queued by the update's graph), `indirect.field_update.threads` (the job thread's job) |
| display | `post` | the colour planes as 8-bit pixels (a power transfer, 2.2 by default, or the piecewise sRGB: a control), a page of the display a tile | `post.show` (SHOW, then the thread's PUSH into the host's memory) | `post.show.threads`: the step `post`, which writes each tile's display page from the core |

**Layers.** With a scene's materials the frame host splits the triangles into up to three
layers by material kind: opaque, masked and glass; each has its own lists. Without
materials there is one layer. Glass behind glass is not drawn: the glass layer is the
nearest transparent surface.

**Views.** A view is what one run of the frame's parts draws: view 0 is the eye's, of kind
COLOUR; a DEPTH view writes the nearest surface's 1/z into its target. The sun's shadow
map is drawn as DEPTH views, one a quadrant of the map.

## The slots between the parts

A **slot** is a named value passed between implementations, with its format and what it
holds (`src/prism_common/slots.py`). A pipeline whose reads are not given or written
earlier is refused when it is made, naming the slot.

| slot | holds | in the threads' form |
|---|---|---|
| `scene.mesh` | the triangles as blocks of 32: corners' positions, then their colours | each layer's mesh blocks |
| `view.camera` | a view's camera: 16 numbers and the frame's grid of tiles | the frame's page |
| `frame.visibility` | per tile the five planes: 1/z, red, green, blue, the triangle number | a plane of the tile thread, kept on the core; no tensor of the frame |
| `frame.lists` | each layer's directory and lists | each layer's lists, written by the place pull |
| `mesh.attributes` | each layer's shade blocks: albedo texel areas, material words, normals, speculars | the same |
| `frame.surface` | each layer's lit surface: two frames of planes | a plane of the tile thread, kept on the core |
| `light.shadow_map` | the sun's shadow map, 1/z in light pages of 32 x 32 | the same |
| `view.depth` | the DEPTH views: their indices, cameras and frame size | the same |
| `elements.radiance`, `elements.irradiance` | `x` and `y` of the transport's apply | the same |
| `light.field`, `light.field_scale` | the field as LIGHT reads it, and its scale | given by the frame's thread from the job thread's `job_wants` |
| `display.picture` | the frame for display: a page a tile, 32 x 32 pixels of R, G, B, 255 | written by the post step; read back by the host |

On the card a slot crosses from one implementation to another by its name only: on the
X280 thread a unit gives or takes it, on the host a host gives its tensor and another
connects to it.

## The presets

A preset is a file of [configs/pipeline](../../configs/pipeline): `PIPELINE`, its
`OPTIONS`, and for the picture presets the reference a frame is compared with and the
judge of its numbers. Its form is chosen once, from its implementations
(`prism.program.form`): the threads' assembly when one implementation's host is the
threads' frame host, else the stage-wise one. `prism.loop.Loop` runs both the same way.

| preset | form | implementations | what it is for |
|---|---|---|---|
| `textured_threads` | threads | `raster.threads`, `material.texture.threads`, `post.show.threads` | the renderer: textured frames; its picture `textured`'s |
| `lit_threads` | threads | and `direct.shadow_pcf`, `direct.light.threads` | the renderer: direct light, the sun's views when it moves; its picture `lit`'s |
| `gi_threads` | threads | and `indirect.transport.threads`, `indirect.field_update.threads`, with `direct.light.threads_field` | the renderer: `lit_threads` with the indirect field, updated by the job thread while frames go on; its picture `gi`'s |
| `raster` | stage-wise | `raster`, `post.show` | visibility with the vertex colours |
| `textured` | stage-wise | `raster`, `material.texture`, `post.show` | the reference picture of `textured_threads` |
| `lit` | stage-wise | and `direct.shadow_pcf`, `direct.light` | the reference picture of `lit_threads` |
| `gi` | stage-wise | `lit`'s with `indirect.transport`, `indirect.field_update` | the reference picture of `gi_threads`; its update blocks the frames |
| `lit_tile`, `gi_tile` | stage-wise | `lit`'s and `gi`'s, with the option `light_shows` (the last LIGHT converts for display, no SHOW command); `gi_tile` also `update_beside` | comparisons: the display in LIGHT, the update on the cluster beside the frames |
| `field` | stage-wise | `indirect.transport`, `indirect.field_update` | the field's update alone |
| `apply` | stage-wise | `indirect.transport` | the transport's apply alone |

The scene's data a preset needs: `raster` the mesh (a generated scene too); the textured
presets a scene with materials (a public scene or an opened glTF file); the lit presets
its lighting; the `gi` presets its indirect files, made once by
`python scripts/data/public_scenes.py indirect <scene>` ([scenes](scenes.md)).

## How a stage gives its parts

An implementation is a folder of `src/prism/stages/<stage>/<implementation>/`. What it
shows the pipeline is its declaration (`prism.core.implementation.Implementation`): the
items it fills, the slots it reads and writes, its class (the stage-wise form's handlers
on every core), its host, its check and its unit (its part of the frame's thread).
`material.texture`'s:

```python
TEXTURE = IMPLEMENTATIONS.register(
    "material.texture",
    Implementation(
        name="material.texture",
        fills=("material",),
        reads=("frame.visibility", "frame.lists"),
        writes=("mesh.attributes", "frame.surface"),
        device=made,
        host=TextureHost,
        check=check,
        thread=UNIT,
    ),
)
```

For the threads' form a stage also gives a **step** (`prism.core.thread.module.Step`,
under its `steps/` folder): its header for the compute CPUs, its list passes, the pages
it may ask for, its outputs, the planes it reads and leaves, the state it keeps on a core
and its words of the frame's page. The threads' implementations
(`src/prism/program/threads/implementations.py`) are the stage-wise declarations with no
class and the threads' host and unit; the handler `work` is composed from the preset's
tile thread and the geometry's kinds ([steps](../internals/program/steps.md)).

An implementation never writes a handler number, a buffer index, a thread region or a
word's place: it says what it needs and `prism.core` assigns it, or refuses with the
numbers. `prism.core.fields` holds the fields several classes share, each sized by its
largest user, and the command space, each stage's parts over the same bytes for the
length of a command.

## The loop

`prism.loop` keeps a pipeline loaded: a frame from a camera, a change of size (a reload
only past the capacity it holds), a recovery from a frame's code (lists grown in the
live run and the frame tried again, or a reload), and every frame's times row kept
across reloads. Controls (the sun, the exposure, the tone curve, each light term, the
bounces, the display's transfer) are set from the host between frames. The command line
and the viewer drive it ([the command line](../guides/cli.md), [the viewer](../guides/viewer.md)).

## Checked against the reference

`prism_reference` holds every algorithm in numpy, by the same stage names, with no
Komorebi and no card. It is the source of the data the card reads and of the pictures a
frame is judged by: each preset's `REFERENCE` and `JUDGE` (pixels that differ, or the
shares over 2, 4 and 8 of 255 apart and the largest error). A threads' preset is judged
by its stage-wise preset's reference and judge; on the scenes of
[the account](../performance/account.md) every threads frame's picture equals the
stage-wise frame's, 0 pixels different. What the checks cover is in
[checks](../guides/checks.md).
