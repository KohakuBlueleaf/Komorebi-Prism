# The environment

The environment variables the repository's code reads, and those of Komorebi that a run
on a card reads.

## Variables

| name | for | default | read in |
| --- | --- | --- | --- |
| `PRISM_DATA` | the data root: generated and public scenes, their materials, lights and indirect files, and what is made from them | none: a call that needs it stops with an error that names it | `src/prism_common/paths.py` (`data_root`) |
| `PRISM_BUILD` | where the compiled helpers (`prism_reference/native`) and the checks' host-built C go | `$PRISM_DATA/build` | `src/prism_common/paths.py` (`build_root`) |
| `PRISM_CACHE` | where caches go: `blocks/<key>/`, each layer's mesh and shade blocks of a scene and its materials, unlit or lit (one `.npy` an array and `key.json`; the key the first 16 hex digits of the digest of the arrays they are made from (`prism_common.digest`: 16 MiB pieces hashed with BLAKE2b on the process's CPUs, then the digest of the pieces' digests), the whole digest kept and compared), made by the first load and read by the next; `counts/<key>.npy` and `<key>.json`, a layer's list entries a tile for a camera, a frame size and a grid (the key of the positions, the indices, the camera, the size and the grid, kept the same way); `apply/`, the transport's weights; the checks' temporary files | `$PRISM_DATA/cache` | `src/prism_common/paths.py` (`cache_root`); `blocks/`: `src/prism/stages/material/texture/model/blocks.py`; `counts/`: `src/prism/stages/raster/model/counts.py` |
| `PRISM_THREADS` | the threads of the native batch tracer | the CPUs the process may use, at most 8 | `src/prism_reference/trace/batch.py` (`threads`) |
| `PRISM_SCENES_EXTRA` | a further JSON file in the layout of `public_scenes.json`, whose scenes are added to the table after the data root's `opened_scenes.json` ([scenes](../concepts/scenes.md)) | none: the table alone | `src/prism_reference/scene/public/table.py` (`table`) |
| `PRISM_BLENDER` | the Blender the artists' scenes are measured, exported and rendered with ([artist scenes](artist_scenes.md)) | `blender` on the `PATH` | `scripts/data/artist_scenes.py` (`blender`) |
| `CXX` | the C++ compiler of the native helpers | `g++`, else `c++`, on the `PATH` | `src/prism_reference/native/build.py` (`find_cxx`) |
| `PRISM_VIEWER_API` | the server `npm run dev` proxies `/api` to, while working on the viewer's page ([viewer](viewer.md)) | `http://127.0.0.1:8790` | `apps/prism_viewer/web/vite.config.js` |

## Komorebi and the card

Komorebi (`komorebi-tt`) is a dependency of the package `prism`; running a preset, the
command line or the viewer needs it installed, with a Blackhole card prepared once by
`kmr setup [--card N]`. `pip install "komorebi-tt[runtime]"` installs it with
`komorebi-runtime`, the pinned tt-metal build, so that a program runs on a card with no
tt-metal tree. The variables it reads that a run of this repository meets:

| name | what Komorebi does with it |
| --- | --- |
| `KMR_CACHE` | the cache directory (default `~/.cache/komorebi`): the native host module built on first use, the dispatcher image, the RISC-V compiler `kmr sfpi` fetches and the runtime root; a new cache directory needs `kmr sfpi` again |
| `TT_METAL_HOME` | a tt-metal tree; set, it always means that tree, and the native module is built against it; unset with `komorebi-runtime` installed, Komorebi takes its tree from the runtime package |
| `TT_VISIBLE_DEVICES` | a session's `card` selects the card through it (an error if the variable already names another card); `kmr setup` without `--card` takes its first card, else 0 |

`prism_reference` needs neither Komorebi nor a card.
