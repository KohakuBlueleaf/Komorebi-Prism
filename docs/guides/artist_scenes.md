# Artists' scenes from Blender

Scenes made by artists reach the renderer from Blender. The workbench is a set of scripts
run inside Blender (`scripts/blender/`), the table of the scenes
(`src/prism_reference/scene/artist/artist_scenes.json`), a driver
(`scripts/data/artist_scenes.py`) and a check of what it writes
(`python -m checks.artist_export`).

## Why not Blender's glTF export alone

Blender's own glTF exporter falls short of a renderer's input in three ways:

- It writes every copy of an instanced mesh as a mesh of its own. On a production set of
  35.5 M drawn triangles, the exported file held 142.36 M triangles in 3.9 GB, with the
  exporter's instancing option on or off.
- It drops area lights and the world.
- It carries only materials built on a Principled BSDF.

The workbench writes each geometry once, at the identity, and its copies as a table of
matrices beside the `.glb`. It writes the area lights, the world and the render settings
to a sidecar JSON, and it lists what it could not carry.

## Commands

Blender is `$PRISM_BLENDER`, else `blender` on the `PATH`. Each script prints one JSON
line. Scripts stored inside a `.blend` are never run (`--disable-autoexec`).

```
python scripts/data/artist_scenes.py list                  # the table with attribution
python scripts/data/artist_scenes.py fetch [KEY ...]       # download, check, unpack
python scripts/data/artist_scenes.py measure [KEY ...]     # stats.json
python scripts/data/artist_scenes.py export [KEY ...] [--frame N]
python scripts/data/artist_scenes.py render [KEY ...] [--size W H] [--samples N]
        [--engines CYCLES EEVEE] [--frame N] [--timeout SECONDS]
python scripts/data/artist_scenes.py planes [KEY ...]     # surface/cycles.npz from truth.exr
python -m checks.artist_export $PRISM_DATA/artist/<KEY>
```

`fetch` writes into `$PRISM_DATA/artist/downloads`, keeps a file already there with the
row's bytes and SHA-256, waits 20 s between two downloads and unpacks an archive into a
folder named after it. The other commands write into `$PRISM_DATA/artist/<key>/`:
`stats.json`, `scene.glb` with `scene.prism.json` and `scene.instances.npz`,
`truth.exr` and `truth.png` (Cycles), `eevee.png` (EEVEE), `surface/cycles.npz` (`planes`).

The scripts run on their own too:
`blender --background <file.blend> --python scripts/blender/<name>.py -- <arguments>`,
with `measure.py <out.json>`, `export.py <out_stem> [--frame N]` and
`render.py <out_stem> --engine CYCLES|EEVEE --size W H [--samples N] [--frame N]`;
`planes.py` runs without a `.blend`:
`blender --background --python scripts/blender/planes.py -- <truth.exr> <out.npz>`.

Cycles writes, besides Combined, the passes the surface's comparison reads: Z, Normal,
Position, UV, Diffuse Color, Glossy Color and Emission. `planes.py` reads the render
layer of the EXR with the most channels (not a composite layer) and writes `combined`,
`depth`, `normal`, `position`, `diffuse_color`, `glossy_color`, `emit` and `uv` as
float32 arrays with `size` (W, H); `normal` and `position` are turned from Blender's axes
to the description's, `(x, y, z) -> (x, z, -y)`
([surface](../internals/reference/surface.md)).

## Geometry keys and copies

`common.copies` walks the depsgraph's object instances of type MESH, CURVE, SURFACE,
FONT and META, and skips those with no triangles. A copy's base is the original object's
name when the object has a modifier or a shape key, or is not a mesh; otherwise it is the
mesh data's name. Its key is the base and a number k: the k-th distinct evaluated mesh
(by its address during the walk) met under that base. Copies of one evaluated mesh share
a key, also when geometry nodes instance it; one object whose geometry nodes emit several
meshes gives one key a mesh. No triangle count decides a key. Each key's mesh is taken at
its first copy, during the walk: a geometry-nodes instance is a temporary that the walk
reuses. The scene is evaluated as the viewport shows it.

`measure.py` counts the keys, the bases, the bases with more than one mesh, the stored
triangles (one mesh a key), the drawn triangles (every copy) and the copies, and records
beside them Blender's own scene statistics (its text and its triangle number), counted
without the keys. It also records objects by type, materials by what they use (a
Principled BSDF reaching the output, image textures on base colour, normal, roughness or
metallic, transmission, emission, volume, displacement), images and their sizes, lights
by type, cameras, armatures, actions, shape-key sets, modifiers, the engine, resolution,
frames, view transform and the text of a README text block.

## The export's files

`<stem>.glb`: one node a geometry key, named `prism_mesh_<i, six digits>` (keys sorted),
at the identity, with its material slots; the cameras and the sun, point and spot lights
under the source objects' names (the source is renamed out of the way while the scene is
built; the `.blend` is never saved), with Blender's own tangents (`export_tangents`). No
animation, skin or morph.

`<stem>.instances.npz`: `node_names` (N names), `starts` (N + 1, int64) and `matrices`
(M, 4, 4) float32, row-major, in glTF's axes. The matrices of key i are
`matrices[starts[i]:starts[i + 1]]`. Every key is in the table, also one with a single
copy: a reader draws a node only at its matrices.

`<stem>.prism.json`:

```
{"version": 1,
 "source": {"file": "<.blend base name>", "blender": "<version>", "frame": N},
 "render": {"size": [W, H], "camera": "<name>", "exposure": float,
            "view_transform": str, "look": str, "gamma": float},
 "world": {"color": [r, g, b], "strength": float, "environment": str | null,
           "rotation": [x, y, z]},
 "area_lights": [{"name": str, "shape": str, "size": [sx, sy], "color": [r, g, b],
                  "power": float, "matrix": [16 floats, row-major]}],
 "instances": {"file": "<stem>.instances.npz"},
 "not_exported": {"materials": [str], "lights": [str], "objects": [str],
                  "triangles": [{"node": str, "expected": int, "written": int}]}}
```

`size` is the render resolution times its percentage. The world is read when a
Background node feeds the output: its colour and strength. An Environment Texture on its
colour is copied beside the stem as `<stem>.world.<extension>`, with the rotation of a
Mapping node feeding it. Any other world gives its viewport colour, strength 1, and
`"world"` in `not_exported.objects`. An area light points along its local -Z; its matrix
is in glTF's axes and `power` is in watts. `not_exported.triangles` lists each node
whose mesh in the written `.glb` holds other than the triangles handed to the exporter
(read back from the `.glb`'s JSON chunk after writing).

## The table

`artist_scenes.json`, one row a key: `name`, `author`, `licence`, `licence_from` (the
file's README, the download page's label or the site's licence page), `url`, `member`
(the `.blend` inside an archive, `""` for a plain file), `bytes` and `sha256` of the
download. `prism_reference.scene.artist.table` reads it.

## The check

`python -m checks.artist_export <folder>` reads the `.glb`'s JSON chunk and the instance
table with numpy, without Blender. It requires that every name in the table is a node
with a mesh, that the meshes' triangles times their copies sum to the drawn triangles of
`stats.json` and the meshes' triangles sum to its stored triangles, with the triangles
of `not_exported.triangles` added back, and that each of its entries holds the `.glb`'s
count: a drop that is recorded passes, one that is not fails. The area lights must match
its AREA lights, the sidecar's render camera (when not null) must be a node of the `.glb`
holding a camera, and the sidecar's version must be 1.

## Not carried yet

- Materials that are not a Principled BSDF: they are listed, not baked.
- Area lights in the `.glb`: they are in the sidecar only.
- Hair curves, point clouds, volumes and grease pencil: listed in
  `not_exported.objects`.
- Animation, armatures and shape keys: the export is one frame, evaluated.
- The render's own evaluation: the depsgraph is the viewport's, so modifiers with other
  render levels and objects hidden only in the render are taken as the viewport shows
  them.
- Triangles the glTF exporter leaves out, each recorded in `not_exported.triangles`.
  Two cases were measured. When a mesh's material uses a tiled (UDIM) image, the
  exporter keeps a triangle only when its first corner lies on an existing tile. In the
  second case, one object lost 20 of its 179 triangles, and the cause was not found.
