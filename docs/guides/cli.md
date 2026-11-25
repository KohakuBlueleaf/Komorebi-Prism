# The command line and the presets

A preset is a file of `configs/pipeline/`: the pipeline (`PIPELINE`), its options
(`OPTIONS`), and what a runner needs to open it on a scene and check its frames. The
command line (`apps/prism_cli`), the preset runner (`scripts/run/preset.py`) and the
viewer's server (`apps/prism_viewer/server`) open a preset the same way, through
`prism_cli.preset.opened`.

## What a preset names

| name | holds |
| --- | --- |
| `PIPELINE` | the implementations, in order, and the pipeline's inputs |
| `OPTIONS` | the options a load takes (`frames` the number a check runs) |
| `SCENE_INPUTS` | the options taken from a public scene's view: `materials`, `name`, `lights` (a preset with any needs a `--view`) |
| `REFERENCE(loop, scene)` | the picture a frame of `scene` (a view at its size) is compared with, at the loop's settings (the sun, the tone and the terms of `lit` included) |
| `JUDGE(loop, scene)` | a function of a frame's picture that gives its numbers against the reference: pixels that differ for `raster`; pixels over 2 apart and the largest error for `textured`; the shares over 2, 4 and 8 and the largest error for `lit` (later pieces of cut triangles apart) |

`opened(name, scene, view, size, options, display)` gives the preset made ready: its
pipeline (without the implementations that fill `post` when `display` is false), its
options (`OPTIONS`, the size, the scene's inputs, then `options`), the scene, the size,
and `open(session)`, `reference(loop, scene)` and `judge(loop, scene)`. It lives in
`apps/` because the presets import `prism`: the package under `src/` does not load them.

## `run`

```
python -m prism_cli run --pipeline lit --scene sponza --view overview --size 1024 1024 \
    --check 0 15 --card 1 [--out FOLDER]
```

A preset's frames on one card along a camera path (`--path still`, the view's own camera;
`--path forward`, the eye stepping 0.05 a frame along the view direction), with sizes
changed on the way (`--resize W H AT`).
`--check FRAME ...` compares those frames' pictures with the preset's `REFERENCE` (pixels
that differ, bit for bit) and gives its `JUDGE`'s numbers; `--pictures` takes every
frame's picture (the host's frame is then the frame and its picture). `--option KEY=VALUE`
updates the options (the value a Python literal, else the text). `--frames` the number of
frames (the preset's `frames` if none, else 1), `--cores` the cores used (every core if
none), `--card` the card (0 by default). The record is printed; with `--out FOLDER` it is
also written there as `<name>.json`, `--name` its stem (by default
`<scene>[_<view>]_<W>_<H>_<path>`). Exit 1 on a frame code that is not 0; the pictures' numbers are
reported, not judged by the command.

The record (one JSON line, and the harness's file under `--out`):

| key | holds |
| --- | --- |
| `ms` | each time column's median and least over the frames, by layer: `part` the first layer's, `part.<i>` layer i's |
| `ms_sum_of_layers` | each column a layer unit gives by layer, summed over the layers of a frame, then its median and least |
| `pictures_judged` | by checked frame: `pixels_differ` against `REFERENCE`, and the `JUDGE`'s numbers |
| `host_ms` | the host's frame (the loop's frame and its picture when taken): median, least, frames a second |
| `codes`, `codes_not_0`, `reloads`, `retries`, `sizes`, `resized`, `results` | the frames' codes, the loop's reloads and retries, the sizes, each frame's result columns |

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

The other scripts are listed in [scripts/README.md](../../scripts/README.md).
