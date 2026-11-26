# glTF scenes

A glTF file (`.glb` or `.gltf`) converted, through the
[scene description](../concepts/scene_description.md), into a scene of the tables: the
same three files and the same table entry a [public scene](../concepts/scenes.md) has.
After the conversion every preset, check and the viewer open the scene by its name,
unchanged. The code is `src/prism_reference/scene/artist/` (`convert.py`, `materials.py`,
`entry.py`); the check is `python -m checks.gltf_scene`.

## One command

```
export PRISM_DATA=<data root>
python -m prism_cli open <file> [--pipeline textured|lit|...] [--size W H] [--card C] \
    [--bake wait|background|none]
```

converts the file once and keeps it, makes the lights in two steps when the preset takes
them, and draws the scene ([the command line](cli.md#open)). The scene's name is
`<stem>_<10 hex digits>`: the stem is the file's own, its folder's when the file is called
`scene`; the digits begin the file's key, the BLAKE2b digest of the bytes of the file, of
its sidecar and the sidecar's instance table when they are there, of the converter's
version (`opened.CONVERTER`) and of `--camera`. The mesh and materials files are written
as below; the entry goes into `<data>/opened_scenes.json`, which the table reads whenever
it exists (`$PRISM_SCENES_EXTRA` is not needed). An open whose key is already in that file
with its files present converts nothing. When the preset takes the lights and the scene
has none, the lighting file is first written with every vertex's sky visibility 1, so the
first lit picture comes before the bake; the bake (`--bake background`, the default) runs
as a process of its own and replaces the file when it ends, and the next open finds the
lights baked. The three commands below are the parts it is made of.

## The parts

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

- `<data>/public/<name>.npz`: the mesh, as `scene.public.mesh.convert` writes it.
  Every drawn mesh node (instances included) is flattened to world space
  (`scene.description.flatten`, at most `--most-triangles`, 4,000,000 by default; over it
  the conversion stops). No ground is added. A triangle's flat colour is its material's
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
camera's roll, a spot light's cone and area lights.

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

```
python scripts/data/public_scenes.py lighting NAME     # environment, visibility bake, shadow map
python scripts/run/preset.py --pipeline lit --scene NAME --view camera
```

The lighting command is the public scenes' own: it downloads the environment map once,
bakes the visibility with the host's tracer and writes `<data>/public/NAME_lighting.npz`.
Both read the entry through `$PRISM_SCENES_EXTRA`, which must stay set.
