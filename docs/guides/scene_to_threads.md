# From a glTF scene to a picture drawn as threads

The one path, in commands: a glTF file opened into a scene, drawn by the renderer as
threads from the command line, then chosen in the viewer. Every command is the one the
stage-wise presets use; only the preset's name changes.

## The threads' presets

| preset | draws as |
| --- | --- |
| `textured_threads` | `textured` |
| `lit_threads` | `lit` (the sun's views when the sun moves) |
| `gi_threads` | `gi` (the field's update as the job thread's job) |

Each draws its stage-wise preset's picture. A threads' preset is a pipeline whose frame
host is the threads' one (`prism.program.threads`); `prism.loop.Loop` chooses the
assembly and the load once, from the pipeline (`prism.program.form`), and runs frames,
sizes, recoveries and camera paths the same way for both forms. When a view needs more
than the program was loaded with, the frame's code is recovered: a layer's lists too
small for the camera grow while the run stays loaded and the frame is tried again
(`retries` in the record; [the raster model](../internals/raster/model.md#the-lists-slots-a-load-holds));
more slices than the capacity after a size change take one reload with what it needed
([the command line](cli.md), `reloads` in the record).

## 1. Open the scene

```
export PRISM_DATA=<data root>
python -m prism_cli open <file>.glb --pipeline lit_threads --size 1920 1080 --card C \
    --out <folder>
```

converts the file once into the data root (an open that finds its key converts nothing),
makes the lights when there are none and draws `--frames` frames as threads, the last
written as `<folder>/<name>_camera_lit_threads.png`; the record (one JSON line) names the
scene `<stem>_<10 hex digits>` ([glTF scenes](gltf_scenes.md)). From then on the scene is
opened by that name with the view `camera`.

## 2. Draw it as threads from the command line

```
python -m prism_cli run --pipeline lit_threads --scene <name> --view camera \
    --size 1920 1080 --frames 64 --path forward --card C
```

64 frames with the eye moving forward; exit 0 when every frame's code is 0. The record's
`codes`, `reloads` and `frames_reloaded` say whether a frame needed a reload, `retries`
whether one was recovered in the live run.
`--resize W H AT` changes the size from frame AT on.

## 3. Choose it in the viewer

```
python -m prism_viewer.server --host 127.0.0.1 --port P --token TOKEN \
    --pipeline lit_threads --scene <name> --view camera --card C
```

The catalog lists every preset that renders a view, the threads' ones included, and every
scene of the data root with its views, the opened ones included; the page chooses the
pipeline and the scene, and moves the camera ([the viewer](viewer.md)). The viewer's
check runs the same on a threads' preset:

```
python -m prism_viewer.server.check --pipeline lit_threads --scene <name> --view camera \
    --card C [--no-reference]
```

The preset's `REFERENCE` and `JUDGE` are the reference's frames on the host, whose time
grows with the scene's triangles; on a scene of millions of triangles `--no-reference`
leaves them out (they only report numbers; every pass or fail of the check stays).
