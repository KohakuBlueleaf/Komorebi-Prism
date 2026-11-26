# glTF scenes

A glTF file (`.glb` or `.gltf`) opened into a scene, drawn by the renderer as threads,
then chosen in the viewer. The file is converted once, through the
[scene description](../concepts/scene_description.md), into a scene of the tables: the
same files and the same kind of table entry a [public scene](../concepts/scenes.md) has.
After the conversion every preset, check and the viewer open the scene by its name. The
code is `src/prism_reference/scene/artist/` (`opened.py`, `convert.py`, `materials.py`,
`entry.py`, `source.py`); the check is `python -m checks.gltf_scene` ([checks](checks.md)).

## 1. Open the file

```
export PRISM_DATA=<data root>
python -m prism_cli open <file>.glb --pipeline lit_threads --size 1920 1080 --card C \
    --out <folder> [--camera NODE] [--bake wait|background|none]
```

converts the file once and keeps it, makes the lights when the preset takes them and the
scene has none, and draws `--frames` frames (16) as threads, the last written as
`<folder>/<name>_camera_lit_threads.png` ([the command line](cli.md#open)). The record
(one JSON line) names the scene `<stem>_<10 hex digits>`: the stem is the file's own, its
folder's when the file is called `scene`; the digits begin the file's key, the BLAKE2b
digest of the name, size and bytes of the file, of its sidecar and the sidecar's instance
table when they are there, of the converter's version (`opened.CONVERTER`) and of
`--camera`. The mesh and materials files are written as below; the entry goes into
`<data>/opened_scenes.json`, which the table reads whenever it exists. An open whose key
is already in that file with its mesh and materials present converts nothing.

When the preset takes the lights (the lit and `gi` presets) and the scene has none, the
lighting file is first written with every vertex's sky visibility 1 and the sun's shadow
map left to the card, so the first lit picture comes before the bake; the bake
(`--bake background`, the default) runs as a process of its own and replaces the file
when it ends, and the next open finds the lights baked.

From then on the scene is opened by its name with the view `camera`.

## 2. Draw it from the command line

```
python -m prism_cli run --pipeline lit_threads --scene <name> --view camera \
    --size 1920 1080 --frames 64 --path forward --card C
```

64 frames with the eye moving forward; exit 0 when every frame's code is 0. The record's
`codes`, `reloads` and `frames_reloaded` say whether a frame needed a reload, `retries`
whether one was recovered in the live run (a layer's lists grown for the camera).
`--resize W H AT` changes the size from frame AT on; `--check 0` compares frame 0 with the
reference made on the host.

## 3. Choose it in the viewer

```
python -m prism_viewer.server --host 127.0.0.1 --port P --token TOKEN \
    --pipeline lit_threads --scene <name> --view camera --card C
```

The catalog lists every preset that renders a view and every scene of the data root with
its views, the opened ones included; the scene menu shows the opened scene's source file,
its triangles drawn and stored, its objects and instances ([the viewer](viewer.md)). The
viewer's check runs the same on a threads' preset:

```
python -m prism_viewer.server.check --pipeline lit_threads --scene <name> --view camera \
    --card C [--no-reference]
```

The preset's `REFERENCE` and `JUDGE` are the reference's frames on the host, whose time
grows with the scene's triangles; on a scene of millions of triangles `--no-reference`
leaves them out (they only report numbers; every pass or fail of the check stays).

## The indirect light

`gi` and `gi_threads` also read the scene's indirect file and its transport set
(`SCENE_FILES`), which neither `open` nor the conversion makes. After the lights:

```
python scripts/data/public_scenes.py indirect <name>
```

([indirect light](../concepts/scenes.md#indirect-light)). Without them the viewer's
catalog refuses both presets on the scene with the reason ("no indirect data; no
transport set").

## The conversion alone

```
export PRISM_DATA=<data root>
export PRISM_SCENES_EXTRA=$PRISM_DATA/extra_scenes.json
python scripts/data/gltf_scene.py convert <file> --name NAME [--camera NODE] \
    [--most-triangles N] [--licence TEXT] [--attribution TEXT] [--workers N]
python scripts/data/gltf_scene.py report <file>
```

`convert` writes the two files under the data root, adds the entry under `NAME` to the
JSON file `$PRISM_SCENES_EXTRA` names (made when missing, its other entries kept) and
prints the report as one JSON object: the description's coverage, the triangles and
vertices written, materials and triangles by kind, each texture with its role, the texel
bytes, each material's mapping (kind, exponent, specular, transmission, slots, what was
dropped), the view, the camera nodes of the file, the notes and the seconds. With
`$PRISM_SCENES_EXTRA` unset it stops and says to set it; a name of a public scene is
refused. `--workers` is the number of texture decoders. `report` prints the
description's coverage alone (`scene.description.report.text`).

## What is written

- `<data>/public/<name>.npz`: the mesh in the public scenes' layout (`positions`,
  `colors`, `indices`, `counts`). Every drawn mesh node (instances included) is flattened
  to world space (`scene.description.flatten`, at most `--most-triangles`: 4,000,000 by
  default for `gltf_scene.py convert`, no limit for `prism_cli open` without the option;
  over it the conversion stops before any array is made). No ground is added. A triangle's flat colour is its material's
  `base_color` rgb times, when it has a base-colour texture, the linear mean of that
  texture (its 1 x 1 mip level, the bytes through the standard sRGB transfer); without a
  material it is the readers' default grey. Vertices are split by colour
  (`shared_vertices`) and shaded by `vertex_shade`.
- `<data>/public/<name>_materials.npz`: every key of `MATERIAL_KEYS` with the shapes and
  types `convert_materials` writes. Material 0 is `(flat)` (triangles without a
  material). The textures are decoded by `decode_image`, made into mip chains by
  `texture_levels` in their role, numbered once per (image, role) on first use and packed
  into `texels`, `mip`, `levels`. A scene without textures holds one white texel (a
  1 x 1 RGBA texture of one level, number 0, in no material's slot), so no table is
  empty.
- The per-triangle `uv`: `uv0` through the base-colour texture's transform (glTF's
  order: scale, then rotation, then offset; the rotation matrix's rows `(cos, sin)` and
  `(-sin, cos)`, as Blender's exporter writes it), then written as `(u, 1 - v)`: the
  description's UV origin is the image's top left, the reference's v runs up. A triangle
  of a primitive without `uv0` gets 0.

- The entry's `source` (`scene/artist/source.py`): the file it was made from (its
  resolved path), its format (`glb`, `gltf`) and bytes, and what the description reads
  in it: `objects` (the nodes that draw a mesh), `instances` (the copies they draw: one,
  or each of their instances), `meshes` (the distinct meshes drawn), `stored_triangles`
  (those meshes' triangles, each once) and `drawn_triangles` (what `flatten` draws). The
  viewer's scene menu shows them ([the viewer](viewer.md)); an entry written before it
  has none, and the menu shows those numbers as unknown.

## The mapping

The renderer's material model has six kinds with Blinn-Phong numbers; a glTF material is
mapped onto it by the first row that fits:

| the glTF material | kind | numbers |
|---|---|---|
| `emissive x emissive_strength` reaches `EMISSIVE_MIN` (0.5) in a channel, or it has an emissive texture | emissive | slot 0 the emissive texture when there is one (base 1, 1, 1), else base = clip(emissive x strength, 0, 1) |
| `alpha_mode` BLEND, or `KHR_materials_transmission` with a `transmissionFactor` above 0 | transparent | transmission = `transmissionFactor x base rgb` with the extension, else `1 - base alpha` in each channel; slot 0 the base-colour texture when there is one |
| no base-colour texture, or the primitive has no `uv0` | flat | base = `base_color` rgb |
| `alpha_mode` MASK | masked | slot 0 the base-colour texture; slot 1 stays -1 (the mask is that texture's alpha) |
| it has a normal texture | lit | slot 0 the base-colour texture, slot 2 the normal texture (role "normal") |
| otherwise | textured | slot 0 the base-colour texture |

For every kind: `exponent` = round(2 / a^2 - 2) with a = roughness^2, clipped to
`EXPONENT_RANGE` (roughness 0.5 gives 30); `specular` = 0.04 (1 - metallic) + base rgb x
metallic; `transmission` 0 unless transparent. A material drawn both with and without
`uv0`, whose kind needs a texture, gets a second, flat row named `<name> (no uv0)`.

## What is dropped

Each is a `dropped` note with its count in the report: the metallic-roughness texture,
the occlusion texture, an emissive material's base-colour texture, a normal texture of a
kind that draws none, the normal scale, a second UV set (texture uses naming it, and
drawn primitives carrying `uv1`), a texture transform on any texture but the base
colour, `double_sided`, `unlit`, every carried material extension but transmission, the
camera's roll, the camera's lens shift (`camera shift`), a spot light's cone (drawn as a
point light) and area lights.

## The view

One view, named `camera` (so the view is `<name>_camera`): the node `--camera` names,
else the sidecar's render camera, else the first node with a camera; a file without one
is refused, and so is an orthographic camera. `eye` is the node's world translation,
`target` the eye plus the node's world -Z axis. `fov` is the angle over the larger side
of the picture: with the aspect a = W / H (the sidecar's render size, else the camera's
`aspectRatio`, else 16 / 9) it is `2 atan(a tan(yfov / 2))` when a >= 1, else `yfov`.
`near` is the camera's `znear` when above 0. The view's up is +Y, so a camera rolled
about its axis loses the roll (noted when its +Y axis is more than 1 degree from the
plane of +Y and its forward axis).

## The lighting

With d the diagonal of the mesh's bounding box and c its centre, `light` is
`[c.x, max.y, c.z]` and `lighting` is:

| key | value |
| --- | --- |
| `environment`, `turn`, `sun_to_sky` | `kloppenheim_05`, 0, 5 |
| `ambient` | 0.35, 0.33, 0.3 |
| `lamp_scale`, `emissive_scale`, `exposure`, `shadow_bias` | 1, 1, 1, 3 |
| `merge_distance`, `radius`, `size` | 0.01 d, 0.2 d, 0.002 d |
| `sun` | from the first directional light: `direction` its node's world -Z axis (the way the light travels), `colour` its colour |
| `lights` | the point and spot lights (a spot as a point) at their nodes' world positions, with their colours |

`sun` and `lights` are present only when the file has such lights; without `lights` the
lamps are found among the emissive triangles, as for a public scene.

## Lights, then a preset

A scene converted by `gltf_scene.py convert` has no lights until they are made:

```
python scripts/data/public_scenes.py lighting NAME     # environment, visibility bake, shadow map
python -m prism_cli run --pipeline lit_threads --scene NAME --view camera --card C
```

The lighting command is the public scenes' own: it downloads the environment map once,
bakes the visibility with the host's tracer and writes `<data>/public/NAME_lighting.npz`
(`--visibility open` and `--shadow card` as `open` makes them:
[scenes](../concepts/scenes.md#lighting)). Both read the entry through
`$PRISM_SCENES_EXTRA`, which must stay set.
