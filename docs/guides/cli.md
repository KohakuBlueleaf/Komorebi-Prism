# The command line and the presets

A preset is a file of `configs/pipeline/`: the pipeline (`PIPELINE`), its options
(`OPTIONS`), and what a runner needs to open it on a scene and check its frames. The
command line (`python -m prism_cli`), the preset runner (`scripts/run/preset.py`), the
checks and the viewer's server open a preset the same way, through
`prism_cli.preset.opened`.

## The presets

The renderer is `gi_threads`: the frame run as threads that the card's cores take
([threads](../concepts/threads.md)); `lit_threads` and `textured_threads` are its smaller
forms, without the indirect light and without any light. The
stage-wise presets run the same items one stage's command after another under the
frame's thread; they are the form the threads' pictures are compared with. A threads'
preset takes its stage-wise preset's scene inputs, scene files, `REFERENCE` and `JUDGE`,
and its options with `tile_thread` (the tile thread it runs) and `push` false added.

| preset | form | draws | reads beside the mesh |
| --- | --- | --- | --- |
| `textured_threads` | threads | visibility, each layer's colour from its materials, the display | materials |
| `lit_threads` | threads | `textured`'s, lit: the sun's views when the sun moves, the direct light with the tone step | materials, lighting |
| `gi_threads` | threads | `lit_threads`' with the indirect field; the field's update the job thread's job | materials, lighting, indirect, transport |
| `raster` | stage-wise | visibility, the vertex colour displayed | |
| `textured`, `lit`, `gi` | stage-wise | the pictures of the three threads' presets above | as above |
| `lit_tile`, `gi_tile` | stage-wise | `lit`'s and `gi`'s, LIGHT's last command converting the colour for display on each tile's owner (no SHOW command); `gi_tile` with the field's update beside the frames | as `lit`, `gi` |
| `apply` | a part alone | the light-transport apply on every core | none named (its host reads the transport set) |
| `field` | a part alone | the indirect field's update, the apply a pass | none named (its hosts read the scene's files) |

The reads are the presets' `SCENE_FILES` (the kinds of `prism_reference.scene.public.files`).
The viewer's catalog refuses a preset on a scene that lacks `materials` or `lighting` when
it reads them. A
preset with a far field (`gi`, `gi_threads`, `gi_tile`: `indirect` and `transport` in its
`SCENE_FILES`) on a scene that lacks its indirect data or its transport set is opened
without it, once, by `preset.opened`: the implementations that fill `indirect` left out,
those that fill no item and read what nobody writes any more left out with them, each of
the preset's `FAR_FIELD_ABSENT` replaced by its choice (`gi_threads`: the light unit that
reads no field version), the term `indirect` taken from `terms`; its other options and its
form stay. Its pictures are then the lit preset's of its form (`lit_threads`', `lit`'s,
`lit_tile`'s). The next open after the files are written loads the whole preset. How the
parts fit: [the renderer](../concepts/renderer.md).

## What a preset names

| name | holds |
| --- | --- |
| `PIPELINE` | the implementations, in order, and the pipeline's inputs (a preset given `view.camera` renders a view) |
| `OPTIONS` | the options a load takes (`frames` the number a check runs) |
| `SCENE_INPUTS` | the options taken from a public scene's view: `materials`, `name`, `lights` (a preset with any needs a `--view`) |
| `SCENE_FILES` | the scene's files it reads beside the mesh; the viewer's catalog refuses the preset on a scene lacking `materials` or `lighting`, with the reason; without `indirect` or `transport` the preset opens without its far field (above) |
| `FAR_FIELD_ABSENT` | (`gi_threads`) each implementation replaced by its choice when the scene has no far field: the light unit that reads no field version |
| `REFERENCE(loop, scene)` | the picture a frame of `scene` (a view at its size) is compared with, at the loop's settings (the sun, the tone and the terms of `lit` included) |
| `JUDGE(loop, scene)` | a function of a frame's picture that gives its numbers against the reference: pixels that differ for `raster`; pixels over 2 apart and the largest error for `textured`; the shares over 2, 4 and 8 and the largest error for `lit` (later pieces of cut triangles apart) |

`opened(name, scene, view, size, options, display)` gives the preset made ready: its
pipeline (without the implementations that fill `post` when `display` is false), its
options (`OPTIONS`, the size, the scene's inputs, then `options`), the scene, the size,
and `open(session)`, `reference(loop, scene)` and `judge(loop, scene)`. It lives in
`apps/` because the presets import `prism`: the package under `src/` does not load them.
`prism.loop.Loop` chooses the assembly and the load once from the pipeline
(`prism.program.form`) and runs frames, sizes, recoveries and camera paths the same way
for both forms.

## `run`

```
python -m prism_cli run --pipeline gi_threads --scene sponza --view overview \
    --size 1920 1080 --check 0 15 --card 0 [--out FOLDER]
```

A preset's frames on one card along a camera path (`--path still`, the view's own camera;
`--path forward`, the eye stepping 0.05 a frame along the view direction), with sizes
changed on the way (`--resize W H AT`, the size from frame AT on, repeatable).
`--check FRAME ...` compares those frames' pictures with the preset's `REFERENCE` (pixels
that differ, bit for bit) and gives its `JUDGE`'s numbers; `--pictures` takes every
frame's picture (the host's frame is then the frame and its picture). `--option KEY=VALUE`
updates the options (the value a Python literal, else the text). `--frames` the number of
frames (the preset's `frames` if none, else 1), `--cores` the cores used (every core if
none), `--card` the card (0 by default). The record is printed; with `--out FOLDER` it is
also written there through the harness as `<name>.json`, `--name` its stem (by default
`<scene>[_<view>]_<W>_<H>_<path>`). Exit 1 on a frame code that is not 0; the pictures'
numbers are reported, not judged by the command. The reference is made on the host by
`prism_reference`; its time grows with the scene's triangles.

When a view needs more than the load holds, the frame's code is recovered: the hosts'
recovery is asked, and a frame takes at most one retry in the live run (a layer's lists
grown for the camera, then the frame tried again: `retries`) and one reload with what the
hosts need (`reloads`) ([the raster model](../internals/raster/model.md#the-lists-slots-a-load-holds)).
A size past the capacity held takes one reload; a smaller one none.

The record (one JSON line, and the harness's file under `--out`):

| key | holds |
| --- | --- |
| `ms` | each time column's median and least over the frames, by layer: `part` the first layer's, `part.<i>` layer i's |
| `ms_sum_of_layers` | each column a layer unit gives by layer, summed over the layers of a frame, then its median and least |
| `pictures_judged` | by checked frame: `pixels_differ` against `REFERENCE`, and the `JUDGE`'s numbers |
| `host_ms` | the host's frame (the loop's frame and its picture when taken): median, least, frames a second |
| `frames`, `rows`, `codes`, `codes_not_0` | the frames run, the times rows read, the distinct codes, the frames whose code is not 0 |
| `reloads`, `retries`, `frames_reloaded`, `frames_retried` | the loop's reloads (each with its reason and seconds) and retries; the frames that needed one |
| `sizes`, `resized`, `results`, `path`, `pictures` | the sizes, each resize (frame, size, reloaded, the host's ms), each frame's result columns, the path, whether every picture was taken |
| `far_field` | null for a preset without a far field; else `present`, or `absent: ` and what the scene lacks ("no indirect data", "no transport set"): the preset then drew without it |

## `open`

```
python -m prism_cli open FILE [--pipeline P] [--size W H] [--camera NODE] [--frames N] \
    [--card C] [--out DIR] [--bake wait|background|none] [--most-triangles N] \
    [--wait-far-field]
```

A glTF file drawn by a preset in one command, through the parts `run` uses
(`preset.opened`, the loop): the file converted once and kept under the data root (its
textures decoded on the CPUs the command may run on, at most 32), or found there
(`prism_reference.scene.artist.opened`, [glTF scenes](gltf_scenes.md)); when the preset
takes the lights and the scene has no lighting file, the lights made with every vertex's
sky visibility 1 and the bake by `--bake` (`background`, the default: a detached
`public_scenes.py lighting NAME --visibility bake --shadow card`, its log
`<data>/public/NAME_bake.log`, or, when the open starts the far field's build, that
build's own bake under its lock and no other ([built at open](gltf_scenes.md#built-at-open));
`wait`: baked first; `none`: not baked), both with the
lights' `shadow` `card`: the sun's shadow map is not rendered on the host, and the
preset's sun command renders it on the card before the first frame is lit
([the lights' shadow](../concepts/scenes.md#lighting)); then `--frames` frames (16) on
the scene's view, the first and the last with their pictures, the last written to
`DIR/<name>_camera_<pipeline>.png`. `--pipeline` is `textured` by default (give
`gi_threads` for the renderer, `textured_threads` or `lit_threads` for its smaller forms;
a file just opened has no far field, so `gi_threads` draws it without the indirect light), `--size` the
view's own if none, `--out` the current folder; `--most-triangles` refuses a file drawing
more triangles, and without it no count is refused (what refuses is the card's capacity or
the host's memory). A scene opened by a preset with the far field and without its files
has the far field built beside the frames; `--wait-far-field` waits for that build, opens
the preset again on a new session and draws `--frames` frames with the far field, the
last picture `DIR/<name>_camera_far_field_<pipeline>.png`. Exit 0; 1 on a frame code that is not 0; 2 when the card refused the
load. The record, one JSON line:

| key | holds |
| --- | --- |
| `name`, `file`, `pipeline`, `key`, `converted` | the scene's name, the file's name, the preset, the scene's key, whether this open converted it (else it was found) |
| `triangles`, `vertices` | what the conversion wrote (only when this open converted) |
| `lights`, `lights_made` | the lights' state after the open (`none`, `open`, `baked`); what this open made, the bake's PID and log (none when the far field's build bakes) |
| `size`, `frames`, `codes`, `picture`, `refused` | the size, the frames run and their codes, the picture's file, the refusal's text |
| `far_field` | as `run`'s: null, `present`, or `absent: ` and what the scene lacks |
| `far_field_build`, `far_field_wait` | the far field's build at open (`started` with its PID and log, `building`, or null); with `--wait-far-field`, the build's record, the seconds waited, the reload's frames, codes, picture and seconds |
| `first_picture_seconds` | from the command's start (`_from_process`: the process's) to the first frame's picture; `seconds` the command's |
| `account.seconds` | each part of the load, exclusive of the tensor writes inside it: `digest`; `convert.<step>` (`import`, `flatten`, `materials`, `textures`, `shared_vertices`, `uv`, `writing`, `entry`); `lights.open` and `lights.open.shadow_map` (the map's camera alone, the map being the card's; or `lights.bake`); `module` (Komorebi's host module); `read.mesh`, `read.materials`, `read.lights`; `session.start`; `model.<implementation>` (its host's prepare and connect); `program.made` (the assembly less its hosts), `program.build`, `program.launch` (the load less the builds and the binds); `bind.<implementation>`; `frame.first`; `frames` (all of them); `other` (the rest) |
| `account.tensors` | the tensors written to the card while the pipeline is opened, by implementation (`load`: outside every host): bytes, seconds, calls |
| `account.builds`, `account.peak_rss_mib` | each program build's seconds and whether it compiled (else found in the cache); the process's peak resident memory (`peak_rss_convert_mib`: right after a conversion, null when the scene was found; `peak_rss_children_mib`: its children's) |

Where those seconds go on four artists' scenes: [measurements/open](../../measurements/open/README.md)
and [the load](../performance/load.md).

## The preset runner

```
python scripts/run/preset.py --pipeline P --scene S [--view V] [--size W H] [--frames N]
    [--cores N] [--card N] [--set NAME=VALUE ...] [--option NAME=VALUE ...]
    [--check MODULE.FUNCTION] [--no-display] [--out FOLDER]
```

opens the preset the same way and runs a check on its loop through the harness: its last
implementation's (`check(loop)`), or the function `--check` names by its dotted path.
`--set` sets a control before the frames (`<implementation>.<name>`, a Python literal);
`--option` gives an option of the preset another value (`bounces=0`, a Python literal);
`--frames` the number of frames (the preset's if none); `--cores` the cores used (every
core if none); `--card` the card (0 by default); `--no-display` the preset without the
implementations that fill `post`. The defaults are `--pipeline raster --scene tiny`. One
JSON line, and the record written to `<out>/<scene>[_<view>]_<W>_<H>.json` (`--out`, by
default `measurements/<pipeline>_frame/`).

The runner runs the stage-wise presets' checks, each against `prism_reference`. A threads'
preset is checked against its stage-wise form, picture for picture, by
`python -m checks.threads_frame` ([checks](checks.md)): its implementations' check takes
both presets, not one loop.

The other scripts are listed in [scripts/README.md](../../scripts/README.md).
