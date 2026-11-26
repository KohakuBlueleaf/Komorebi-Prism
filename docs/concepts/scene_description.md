# The scene description

`prism_reference.scene.description` is one description of a scene, filled by an importer
from a scene file and read by everything after it, never the file format itself. The
importer is glTF 2.0 (`prism_reference.scene.importers.gltf`). What reads the description:
the conversion into a scene of the tables, which every preset and the card's hosts then
open ([glTF scenes](../guides/gltf_scenes.md)); the reference's surface
(`prism_reference.material`) and its direct light of a described scene
(`prism_reference.direct.described`), which the comparisons with Cycles use
([artists' scenes](../guides/artist_scenes.md)).

## What it holds

Plain dataclasses of numpy arrays (`description/types.py`):

| type | holds |
| --- | --- |
| `Scene` | lists of `nodes`, `meshes`, `materials`, `textures`, `images`, `samplers`, `lights`, `cameras`; `world` and `render` (or None); `animations` and `skins` (the source's JSON objects, carried, not interpreted); `source` (`path`, `format`, `bytes`, and `file`: counts over the whole file, every scene: `scenes`, `nodes`, `instanced_nodes`); `notes` |
| `Node` | `name`, `parent` (-1 for a root), `local` and `world` (4, 4) float64 (`world` is the product down from the root), `mesh`, `camera`, `light` (-1 for none), `instances` ((N, 4, 4) float32 world transforms of the copies of the node's mesh; when set, the node's own `world` is not drawn), `moving` (an animation targets the node or an ancestor, or it has a skin) |
| `Mesh`, `Primitive` | a primitive's `positions` (V, 3), `normals` (V, 3), `tangents` (V, 4), `uv0`, `uv1` (V, 2), `colors` (V, 4), all float32 (None when absent), `indices` (T, 3) uint32, `material`, `carried` (joints, weights, morph targets as arrays, untouched) |
| `Material` | metallic-roughness factors and textures, normal scale, occlusion strength, emissive and its strength, alpha mode and cutoff, double sided, unlit; `carried`: every other extension's JSON by its name. Defaults are glTF's |
| `TextureUse` | a texture index, its UV set (0 or 1), `offset`, `rotation`, `scale` (`KHR_texture_transform`; identity when absent) |
| `Texture`, `Sampler`, `Image` | an image and sampler (-1: the default); wrap modes `REPEAT`, `CLAMP`, `MIRROR` and filters by glTF's names; an image's `mime`, `width`, `height` read from the PNG, JPEG or WebP header (0, 0 for another format) and its `uri` (a path beside the file) or `data` (a zero-copy view of the bytes). Images are never decoded here |
| `Light` | `kind` (`directional`, `point`, `spot`, `area`), `color`, `intensity` (lux for directional, candela for point and spot, watts for area), `range`, cone angles; an area light's `shape` and `size` |
| `Camera` | perspective (`yfov`, `aspect` or None) or orthographic (`xmag`, `ymag`); `znear`, `zfar` (None when absent); the lens shift `shift_x`, `shift_y` in units of the fitted side and `sensor_fit`, the side whose field of view is kept at another aspect (`""` or `VERTICAL`: `yfov`; `AUTO`: the longer side), both from the sidecar |
| `World`, `Render` | the background colour, strength, environment image and its rotation; the render size, camera node, exposure, view transform, look and gamma |
| `Note` | `kind`, `what`, `count`, `detail` |

### Conventions

Metres, +Y up, right-handed, counter-clockwise front faces, linear colour factors.
Matrices are row-major and act on column vectors (`world @ [x, y, z, 1]`). The UV origin
is the image's top left (glTF's). An index into a list is an int, -1 for none.

### Notes

Every scene carries notes of what the importer did with each kind of thing:

- `used`: read into the description (meshes, primitives, materials, nodes, each extension read).
- `carried`: kept as the source's data, not interpreted (animations, skins, primitive
  joints and weights, each material extension not read).
- `computed`: made by the importer (node world matrices).
- `refused`: a required extension that is not read and does not stop the load.
- `dropped`: left out (primitives of a mode other than triangles, nodes outside the
  default scene, what the exporter could not write as the sidecar lists it).

## What reads it

- `check(scene)` (`description/check.py`) raises `ValueError` naming the first failure: an
  index out of its list, an index at or past its primitive's vertex count, an attribute
  whose length is not V, a non-finite position or matrix, a parent cycle.
- `flatten(scene, most_triangles)` (`description/flatten.py`) draws every node with a mesh
  once at its `world`, or once at each of its `instances`, into world-space `positions`,
  unit `normals` (through the inverse transpose; zeros where a primitive has none), `uv0`,
  `indices` and a per-triangle `material`. The triangle count is computed before any
  array is made; over `most_triangles` it is a `ValueError` with both numbers. A copy with
  a negative determinant has its winding flipped.
- `coverage(scene)` and `text(report)` (`description/report.py`) count what a scene
  holds: nodes, meshes, primitives, stored triangles (the sum over meshes), drawn
  triangles (as `flatten` draws), instanced nodes kept and in the whole file
  (`file_instanced_nodes`), instances, materials by alpha mode and by texture kind,
  each image's largest side, lights by kind, cameras, moving nodes and the notes by kind.

## The glTF importer

`load(path)` reads a `.glb` or a `.gltf` (external buffers and base64 data URIs). The file
and each external buffer are memory-mapped; an accessor whose stored type already is the
description's (float32 attributes, uint32 indices) is a view over the mapped bytes, with
`byteStride` as the view's stride, so a file of several gigabytes loads without being
read into memory.

- Accessors: every component type (5120 to 5126) and type (`SCALAR` to `MAT4`, matrix
  columns padded to four bytes as glTF lays them out), `byteStride`, `normalized`
  integers converted to float32 by glTF's rule (`c / max`, and at least -1 for signed).
  A sparse accessor is read by glTF's rule: the base is its buffer view when it has one,
  else zeros of its count and type; `sparse.indices` (unsigned 8, 16 or 32 bit) name the
  elements that `sparse.values` (the accessor's own component type and type) replace.
  The result is a new array, never a view; exporters write morph targets this way.
- Primitives: triangles (mode 4), indexed or not. Any other mode is dropped with a note.
- Extensions read: `KHR_lights_punctual`, `KHR_materials_emissive_strength`,
  `KHR_texture_transform`, `KHR_materials_unlit`, `EXT_mesh_gpu_instancing` (its
  translation, rotation and scale composed with the node's world matrix into
  `instances`). Every other material extension is carried in `Material.carried`, with a
  note per name. `KHR_draco_mesh_compression`, `EXT_meshopt_compression` and
  `KHR_texture_basisu` in `extensionsRequired` are refused with a `ValueError` naming the
  extension.
- The file's default scene (`scene`, else scene 0) is kept; nodes outside it are not,
  with a `dropped` note of their count. Meshes, materials, lights and cameras keep the
  file's lists and indices. `source["file"]` counts scenes, nodes and instanced nodes
  over the whole file, whichever scene they belong to.

### The sidecar

When `<stem>.prism.json` lies beside the file, it is applied after the glTF:

```
{"version": 1,
 "source": {"file": str, "blender": str, "frame": int},
 "render": {"size": [W, H], "camera": "<node name>", "shift": [x, y],
            "sensor_fit": "AUTO" | "HORIZONTAL" | "VERTICAL", "exposure": float,
            "view_transform": str, "look": str, "gamma": float},
 "world": {"color": [r, g, b], "strength": float, "environment": str | null,
           "rotation": [x, y, z]},
 "area_lights": [{"name": str, "shape": "RECTANGLE" | "SQUARE" | "DISK" | "ELLIPSE",
                  "size": [sx, sy], "color": [r, g, b], "power": float,
                  "matrix": [16 floats, row-major, glTF axes]}],
 "instances": {"file": "<stem>.instances.npz"} | null,
 "not_exported": {"materials": [str], "lights": [str],
                  "objects": [str | {"name": str, "type": str, "reason": str}]}}
```

`world` becomes `Scene.world`; `render` becomes `Scene.render`, its camera found by node
name, and that camera takes the `shift` and `sensor_fit`. Each area light becomes a `Light`
of kind `area` (intensity in watts) on a new root node with that matrix. Each
`not_exported` entry becomes a `dropped` note (`material not exported`, `light not
exported`, `object not exported`; an object's detail `name: reason`). The sidecar, the
area lights and the instance table each add a `used` note. Other keys of the sidecar (the
workbench's `materials` record, `not_exported.triangles`) are not read here. An unknown
`version` or camera name is a `ValueError`.

The instance table is an `.npz` with `node_names` (N,) str, `starts` (N + 1,) int64 and
`matrices` (M, 4, 4) float32 (world transforms in glTF axes): the node named
`node_names[i]` gets `instances = matrices[starts[i]:starts[i + 1]]`. A name with no node
is a `ValueError`.

## The check

```sh
python -m checks.scene_description                       # round trips and refusals
python -m checks.scene_description --files <folder>      # every .glb of a folder
python -m checks.scene_description --box <Box.glb>       # Khronos' Box sample
```

Without arguments the check writes a `.glb` and a `.gltf` (external `.bin`, one data URI)
of a small scene under `$PRISM_CACHE` holding every attribute, every accessor component
type, a strided view, normalized attributes, a sparse accessor with a base view and one without, a two-level
node tree, an instanced node,
each kind of punctual light, two cameras and a material with every field and a texture
transform, then a sidecar and an instance table for it, and compares every value read
with the value written (exact for integers, 1e-6 for floats), `flatten`'s copies with
numpy's own product (and each sparse accessor with numpy's own substitution), and each
refusal. `--files` loads, checks and reports every `.glb`
of a folder, smallest first, with its load seconds and the process's peak resident
memory; where `<name>.json` lies beside a file (counts made from the file's JSON), the
stored triangles, materials, images, cameras, punctual lights and the whole file's
instanced nodes (`source["file"]`) must equal its `mesh_triangles`, `materials`, `images`, `cameras`, `lights` and
`instanced_nodes`. `--box` checks Khronos' `Box.glb`: 12 triangles, 24 vertices, bounds
-0.5 to 0.5 on every axis, one material with base colour (0.8, 0, 0, 1) and metallic 0.
It prints one JSON line with `ok`; exit 1 on a difference.
