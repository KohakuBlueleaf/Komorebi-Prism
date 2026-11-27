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
python -m prism_cli open <file>.glb --pipeline gi_threads --size 1920 1080 --card C \
    --out <folder> [--camera NODE] [--bake wait|background|none]
```

converts the file once and keeps it, makes the lights when the preset takes them and the
scene has none, and draws `--frames` frames (16) as threads, the last written as
`<folder>/<name>_camera_gi_threads.png` ([the command line](cli.md#open)). The record
(one JSON line) names the scene `<stem>_<10 hex digits>`: the stem is the file's own, its
folder's when the file is called `scene`; the digits begin the file's key, the BLAKE2b
digest of the name, size and bytes of the file, of its sidecar and the sidecar's instance
table when they are there, of the converter's version (`opened.CONVERTER`) and of
`--camera`. What only the display reads is not in it: the view's tables
(`<stem>.view.npz` beside the sidecar) and the sidecar's exposure are read whenever a
preset loads the scene's lights, so adding the tables later keeps the key (editing the
sidecar's bytes does change it). The mesh and materials files are written as below; the entry goes into
`<data>/opened_scenes.json`, which the table reads whenever it exists. An open whose key
is already in that file with its mesh and materials present converts nothing.

The entry also keeps, for each of those files, its resolved path, size, modification and
change times (in nanoseconds), device and inode, with `--camera` (`opened.file_stats`).
A later open first reads these from the files and, when an entry of this converter holds
the same values and its mesh and materials are present, takes that entry's key and name
without reading the files' bytes. What this trusts: a file whose bytes change gets a new
change time (`st_ctime`), which the file system sets on every write, rename or copy into
place and which no user call can set back; a file moved, copied, touched or replaced
fails the comparison. When no entry matches (the first open, a changed file, a file
reached by another path, a data root copied to another disk), the open digests the files
as above and, when that key is kept, writes the files' new values into its entry.

When the preset takes the lights (the lit and `gi` presets) and the scene has none, the
lighting file is first written with every vertex's sky visibility 1 and the sun's shadow
map left to the card, so the first lit picture comes before the bake; the bake
(`--bake background`, the default) runs as a process of its own and replaces the file
when it ends, and the next open finds the lights baked. The scene has no indirect file
and no transport set yet: `gi_threads` (and `gi`, `gi_tile`) draws it without the far
field, its picture `lit_threads`', the record's `far_field` `absent: ` with what the scene
lacks ([the indirect light](#the-indirect-light)); the open starts the far field's build
beside its frames, and `--wait-far-field` waits for it and draws again with it.

From then on the scene is opened by its name with the view `camera`.

## 2. Draw it from the command line

```
python -m prism_cli run --pipeline gi_threads --scene <name> --view camera \
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
    --pipeline gi_threads --scene <name> --view camera --card C
```

The catalog lists every preset that renders a view and every scene of the data root with
its views, the opened ones included; the scene menu shows the opened scene's source file,
its triangles drawn and stored, its objects and instances ([the viewer](viewer.md)). The
viewer's check runs the same on a threads' preset:

```
python -m prism_viewer.server.check --pipeline gi_threads --scene <name> --view camera \
    --card C [--no-reference]
```

The preset's `REFERENCE` and `JUDGE` are the reference's frames on the host, whose time
grows with the scene's triangles; on a scene of millions of triangles `--no-reference`
leaves them out (they only report numbers; every pass or fail of the check stays).

## The indirect light

`gi`, `gi_threads` and `gi_tile` also read the scene's indirect file and its transport set
(`SCENE_FILES`: the far field), which the conversion does not make.

### Built at open

When `prism_cli open` or the viewer opens a scene converted from a file (its entry has
`opened`) that lacks them, `preset.opened(..., build=True)` starts their build
(`apps/prism_cli/far_field.py`) as a process of its own under `nice -n 19` and the idle
scheduling class, so the frames keep their CPUs; the frames go on without the far field
meanwhile. The build runs the steps of the commands below: the sky's visibility bake and
the lights (`--visibility bake`) when the lighting file is not baked, then
the block-by-block transport (`--transport sketch`). It writes into a folder of its own,
`<data>/public/.far_field/<name>/`, which links the scene's mesh, materials and
downloads; when every file is written it renames the visibility and lighting files, the
transport folder and, last, the indirect file into `<data>/public/`, so a scene never
holds a part of its far field. A build that fails or is stopped leaves nothing in place
and is started again at the next open. The lock `<data>/public/.far_field/<name>.lock`
lets one build run a scene: a second open finds it held and starts none (its record's
`far_field_build` is `building`). The build's record (what it made, its seconds by step,
or `failed` and the error) is `<data>/public/.far_field/<name>.json`, its log beside it.

The open's record gives `far_field_build` (`started` with its process and log,
`building`, or null when there was nothing to build); with `--wait-far-field` it waits
for the build, opens the preset again on a new session and draws its frames, the last
picture `<name>_camera_far_field_<pipeline>.png`, and `far_field_wait` holds the build's
record, the seconds waited and the reload's seconds. The viewer looks for the files once
a second between frames; when they are there it notices "far field built: reloading" and
opens the preset again once. When the open starts this build, its bake is the only one: `open`'s
`--bake background` (the default) starts no bake of its own then.

### By hand

After the lights, one of the two builds
([the transport's build](../performance/transport_build.md)):

```
python scripts/data/public_scenes.py indirect <name> --transport sketch   # block by block
python scripts/data/public_scenes.py indirect <name>                      # dense
```

([indirect light](../concepts/scenes.md#indirect-light)). Without them the preset is
opened without the far field ([presets](cli.md#the-presets)); the viewer's scene menu
shows the scene's Far field as `none` and its load notice says "without the far field"
([the viewer](viewer.md)). The next open after the files are written loads the whole
preset.

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
  into `texels`, `mip`, `levels`. Each mip chain is kept under the cache root
  (`$PRISM_CACHE`, else `<data>/cache`) in `levels/`, keyed by the BLAKE2b digest of the
  image's bytes, its role, Pillow's version and `materials.LEVELS_VERSION`, so the same
  image in another file or another export is decoded once. A scene without textures holds one white texel (a
  1 x 1 RGBA texture of one level, number 0, in no material's slot), so no table is
  empty.
- The per-triangle `uv`: the UV set the material's base-colour texture names (`uv0` or
  `uv1`; `uv0` without a base-colour texture) through that texture's transform (glTF's
  order: scale, then rotation, then offset; the rotation matrix's rows `(cos, sin)` and
  `(-sin, cos)`, as Blender's exporter writes it), then written as `(u, 1 - v)`: the
  description's UV origin is the image's top left, the reference's v runs up. A triangle
  of a primitive without that set gets 0.
- Per material and texture slot, `uv_maps` (M, 4, 2, 3): the map from the stored uv to
  the slot's own, `(a u + b v + c, d u + e v + f)`, which is the slot's transform after
  undoing the base colour's (`scene/artist/slots.py`; the identity for the base colour
  itself and for a slot without a transform of its own). And `normal_scale` (M,), the
  normal texture's `scale`, which multiplies the normal's x and y before the frame turns
  it. A materials file written without the two reads as the identity maps and scale 1.

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
| `emissive x emissive_strength` reaches `EMISSIVE_MIN` (0.5) in a channel, or it has an emissive texture | emissive | base = clip(emissive x strength, 0, 1) (glTF's emission: the texture times the factor times the strength); slot 0 the emissive texture when there is one |
| `alpha_mode` BLEND, or `KHR_materials_transmission` with a `transmissionFactor` above 0 | transparent | with coverage `c` (base alpha under BLEND, else 1), `t` the `transmissionFactor` (0 without the extension) and `m` metallic: transmission = `1 - c + c t (1 - m) base rgb`; the own diffuse `c (1 - t)(1 - m) base rgb`, stored as base = that over `1 - max transmission` (0 when nothing is left); specular = `c` x the specular below; shadow = `1 - c` (a refractive surface lets no direct light through, as Cycles; under BLEND the share alpha does not cover); slot 0 the base-colour texture when there is one |
| no base-colour texture, or the primitive has not the UV set it names | flat | base = `base_color` rgb |
| `alpha_mode` MASK | masked | slot 0 the base-colour texture; slot 1 stays -1 (the mask is that texture's alpha) |
| it has a normal texture | lit | slot 0 the base-colour texture, slot 2 the normal texture (role "normal") |
| otherwise | textured | slot 0 the base-colour texture |

For every kind: `exponent` = round(2 / a^2 - 2) with a = roughness^2, clipped to
`EXPONENT_RANGE` (roughness 0.5 gives 30); `specular` = 0.04 (1 - metallic) + base rgb x
metallic (times the coverage for transparent); `transmission` 0 unless transparent. A material drawn both with and without
its UV set, whose kind needs a texture, gets a second, flat row named `<name> (no uv0)`.

## What is dropped

Each is a `dropped` note with its count in the report: the metallic-roughness texture,
the occlusion texture, an emissive material's base-colour texture, a normal texture of a
kind that draws none, a texture slot reading another UV set than its material's base
colour (the slot is read on the base colour's set, as the identity map), `double_sided`, `unlit`, every carried material extension but transmission, the
camera's roll, a spot light's cone (drawn as a
point light) and area lights.

That is what the conversion drops of a glTF file. What a file exported from Blender
lacks of its `.blend` is lost before it, in the exporter: `scripts/blender/exportable.py`
reads per material how Blender's glTF exporter writes it, weighted by triangles, area
and picture share, and the scenes the plain export keeps coherent are in
[the glTF truth](../performance/gltf_truth.md)
([artists' scenes](artist_scenes.md#the-same-gltf-as-the-truth)).

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
| `lamp_scale`, `emissive_scale`, `exposure`, `shadow_bias` | 1, 1, 1 (the sidecar's `render.exposure` replaces it when the lights are loaded), 3 |
| `merge_distance`, `radius`, `size` | 0.01 d, 0.2 d, 0.002 d |
| `sun` | from the first directional light: `direction` its node's world -Z axis (the way the light travels), `colour` its colour |
| `lights` | the point and spot lights (a spot as a point) at their nodes' world positions, with their colours |

`sun` and `lights` are present only when the file has such lights; without `lights` the
lamps are found among the emissive triangles, as for a public scene.

### The file's own lighting (`file_lights`)

When the file has a directional, point or spot light or a world (the sidecar's), the
entry also holds the file's own lighting under `file`, in radiometric units (the
reference's [described light](../internals/reference/described_light.md): 683 lumens a
watt, as Blender's exporter writes them). It is drawn only with the option `file_lights`
(`--option file_lights=True`); without it everything above is what is drawn.

| key | value |
| --- | --- |
| `sun` | the first directional light: `direction` its node's world -Z axis, `colour` its colour, `irradiance` colour x lux / 683 (W/m^2) |
| `lights` | each point, spot and area light: `kind`, `position` (its node's, an area light's centre), `colour`, `intensity` (candela / 683, W/sr; an area light power / pi), a spot's `axis`, `inner`, `outer`, an area light's `axis` (its emitting normal) and `area` |
| `world` | the sidecar's world: `colour` and `strength`, or `environment` (the map's resolved path), `strength` and `rotation`; null without one |
| `exposure` | 1 (the sidecar's `render.exposure` replaces it when the lights are loaded) |
| `turn`, `ambient`, `lamp_scale`, `emissive_scale`, `shadow_bias` | 0, (0, 0, 0), 1, 1, 3 |
| `merge_distance`, `radius`, `size` | 0.01 d, 10 d, 0.002 d |
| `notes` | what the file's lighting drops or stands in for |

The lights file holds it beside the defaults' arrays, each named `file_` and the
default's name (`direct.prepare.file_part`): the sun's irradiance and direction as they
are (no sun: irradiance 0); each lamp its colour, intensity and shape (`file_lamp_shape`),
so LIGHT's lamp term `I max(0, n.l) / (d^2 + s^2)` is the irradiance of the file's light
(`radius` 10 d leaves the window at 1 inside the scene); the sky's 9 coefficients
projected from the world's radiance over the map's own grid of directions (Blender's
equirectangular lookup with the world's rotation), and the background's octahedral map
from the same radiance (side 2,048 for a map, 32 for a colour); the shadow camera only
where the file's sun is not the defaults'. A map the reference does not read (`.exr`) is
replaced by the world's colour, with a note in `file_counts` saying why;
`scripts/blender/world_map.py` converts it once (the export writes `.hdr` itself). A
spot keeps its cone, and an area light is carried as a stand-in: a lamp at its centre
whose intensity falls as a cosine about its normal, unshadowed (LIGHT's lamp shape:
[direct light](../internals/direct/light_model.md#lights-table)), drawn only with the
option `area_lights` too. The loader (`direct.lights.load`) reads the `file_` arrays only
under the option; without it the file is read as before.

## Lights, then a preset

A scene converted by `gltf_scene.py convert` has no lights until they are made:

```
python scripts/data/public_scenes.py lighting NAME     # environment, visibility bake, shadow map
python -m prism_cli run --pipeline gi_threads --scene NAME --view camera --card C
```

The lighting command is the public scenes' own: it downloads the environment map once,
bakes the visibility with the host's tracer and writes `<data>/public/NAME_lighting.npz`
(`--visibility open` as `open` makes them:
[scenes](../concepts/scenes.md#lighting)). Both read the entry through
`$PRISM_SCENES_EXTRA`, which must stay set.
