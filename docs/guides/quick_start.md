# Quick start

From a machine with a prepared Blackhole card and Komorebi installed to a picture of a
glTF file drawn on the card, then the same scene steered in the viewer. The machine, the
packages and the card's one-time setup (`kmr setup`) are in the README's "Running it";
the variables every command reads are in [the environment](environment.md).

## 1. Install the repository

```sh
git clone https://github.com/KohakuBlueleaf/Komorebi-Prism && cd Komorebi-Prism
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[viewer,scenes]"    # komorebi-tt and its runtime come from PyPI
kmr setup --card 0                   # once per card
export PRISM_DATA=$HOME/prism-data   # the data root: scenes, lights, caches
```

Install from a clone: the presets (`configs/pipeline/`), the kernels' sources and the
viewer's page are read from it. `viewer` and `scenes` are the extras that bring Pillow
(the viewer's JPEG frames, the textures' decoding).

## 2. Choose a preset

The renderer is the frame run as threads that the card's cores take: the presets
`textured_threads`, `lit_threads` and `gi_threads`. Each has a stage-wise form (`textured`,
`lit`, `gi`: one stage's command after another) whose picture it is compared with; both
forms load from the same scene files and draw the same picture
([presets](cli.md#the-presets)). This page uses `lit_threads`: visibility, the materials,
the sun with its shadow, the sky, the lamps and the display.

## 3. A picture from a glTF file

```sh
python -m prism_cli open <file>.glb --pipeline lit_threads --size 1920 1080 --card 0 \
    --out pictures
```

The command converts the file once into the data root (an open of the same file later
finds it and converts nothing), makes the scene's lights (first with the sky's visibility
1 at every vertex, the bake then running as a process of its own), loads the preset on
the card and draws 16 frames from the file's camera. The last picture is written to
`pictures/<name>_camera_lit_threads.png`, and one JSON line is printed: the scene's name,
the frames' codes, the seconds to the first picture and the account of the load
([the command line](cli.md#open)). The file needs a perspective camera; a file without one
is refused. What the conversion keeps and drops: [glTF scenes](gltf_scenes.md).

The record's `name` is the scene's name from now on, `<stem>_<10 hex digits>`, with one
view, `camera`.

## 4. Frames along a path

```sh
python -m prism_cli run --pipeline lit_threads --scene <name> --view camera \
    --size 1920 1080 --frames 64 --path forward --check 0 --card 0
```

64 frames with the eye stepping forward along the view; frame 0's picture is compared with
the preset's reference, made on the host by `prism_reference` (its time grows with the
scene's triangles). The JSON line gives the card's time columns, the host's frame, the
codes, the reloads and the live retries, and the picture's numbers. Exit 0 when every
frame's code is 0.

## 5. The viewer

```sh
(cd apps/prism_viewer/web && npm install && npm run build)
python -m prism_viewer.server --host 127.0.0.1 --port 8790 --token TOKEN \
    --pipeline lit_threads --scene <name> --view camera --card 0 \
    --offer textured_threads lit_threads gi_threads
```

Open `http://127.0.0.1:8790/?token=TOKEN`, click the frame and steer with W, A, S, D, Q,
E and the mouse. `--offer` keeps the menus to the threads' presets and the scenes they run
on; without it every preset and scene of the data root is offered
([the viewer](viewer.md)). Node.js and npm build the page once.

## A public scene instead

The tables also name public test scenes, downloaded from their sources
([scenes](../concepts/scenes.md)). For Sponza:

```sh
python scripts/data/public_scenes.py fetch sponza        # the mesh and its views
python scripts/data/public_scenes.py materials sponza    # its textures
python scripts/data/public_scenes.py lighting sponza     # the sky map, sun, sky, lamps
python -m prism_cli run --pipeline lit_threads --scene sponza --view overview \
    --size 1920 1080 --check 0 --card 0
```

## The indirect light

`gi_threads` (and `gi`) adds the indirect light, which reads two more files of the scene:
its indirect file and its transport set, made on the host after the lights:

```sh
python scripts/data/public_scenes.py indirect <scene>
```

A scene without them cannot run `gi` or `gi_threads`; the viewer's catalog says so with
the reason ("no indirect data; no transport set").
