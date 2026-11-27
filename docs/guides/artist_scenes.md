# Artists' scenes from Blender

Scenes made by artists reach the renderer from Blender. The workbench is a set of scripts
run inside Blender (`scripts/blender/`), the table of the scenes
(`src/prism_reference/scene/artist/artist_scenes.json`), a driver
(`scripts/data/artist_scenes.py`) and a check of what it writes
(`python -m checks.artist_export`).

## Why not Blender's glTF export alone

Blender's own glTF exporter falls short of a renderer's input in three ways:

- It writes every copy of an instanced mesh as a mesh of its own, with the exporter's
  instancing option on or off, so a set of many copies grows by their count.
- It drops area lights and the world.
- It carries only materials built on a Principled BSDF, and of those only images linked
  straight (or through a Mapping, a Separate Color or a Normal Map node) to its inputs.

The workbench writes each geometry once, at the identity, and its copies as a table of
matrices beside the `.glb`. It rewrites every material of the copy as a plain Principled
BSDF (below), writes the area lights, the world and the render settings to a sidecar JSON,
and it lists what it could not carry.

## Commands

Blender is `$PRISM_BLENDER`, else `blender` on the `PATH`. Each script prints one JSON
line. Scripts stored inside a `.blend` are never run (`--disable-autoexec`).

```
python scripts/data/artist_scenes.py list                  # the table with attribution
python scripts/data/artist_scenes.py fetch [KEY ...]       # download, check, unpack
python scripts/data/artist_scenes.py measure [KEY ...]     # stats.json
python scripts/data/artist_scenes.py export [KEY ...] [--frame N] [--plain]
python scripts/data/artist_scenes.py render [KEY ...] [--size W H] [--samples N]
        [--engines CYCLES EEVEE] [--frame N] [--timeout SECONDS]
python scripts/data/artist_scenes.py planes [KEY ...]     # surface/cycles.npz from truth_gltf.exr
python scripts/data/artist_scenes.py gltf_truth [KEY ...] [--size W H] [--samples N]
        [--engines CYCLES EEVEE] [--timeout SECONDS]
python scripts/data/artist_scenes.py selftest             # the material rewrite's check
python -m checks.artist_export $PRISM_DATA/artist/<KEY>
```

`fetch` writes into `$PRISM_DATA/artist/downloads`, keeps a file already there with the
row's bytes and SHA-256, waits 20 s between two downloads and unpacks an archive into a
folder named after it. The other commands write into `$PRISM_DATA/artist/<key>/`:
`stats.json`, `scene.glb` with `scene.prism.json` and `scene.instances.npz`,
with `render` `blend_cycles.exr` and `blend_cycles.png` (Cycles on the artist's `.blend`),
`blend_eevee.png` (EEVEE on it), with `gltf_truth` `scene_gltf.blend`, `truth_gltf.exr` and
`truth_gltf.png` (Cycles), `eevee_gltf.png` (EEVEE)
([the same glTF as the truth](#the-same-gltf-as-the-truth)), and with `planes`
`surface/cycles.npz` (the passes of `truth_gltf.exr`). A `.blend` render is never the
truth: the truth is Cycles reading the same glTF the renderer reads.

The scripts run on their own too:
`blender --background <file.blend> --python scripts/blender/<name>.py -- <arguments>`,
with `measure.py <out.json>`, `export.py <out_stem> [--frame N] [--plain]` and
`render.py <out_stem> --engine CYCLES|EEVEE --size W H [--samples N] [--frame N]`;
`planes.py` and `from_gltf.py` run without a `.blend`:
`blender --background --python scripts/blender/planes.py -- <truth_gltf.exr> <out.npz>`,
`blender --background --python scripts/blender/from_gltf.py -- <stem> <out.blend>`.

Cycles writes, besides Combined, the passes the surface's comparison reads: Z, Normal,
Position, UV, Diffuse Color, Glossy Color, Emission and Object Index. Before the render,
`render.py` numbers every object of the file in that session (its pass index is its row,
from 1, objects sorted by name; 0 is none) and writes the rows' names and types to
`truth.objects.json`. `planes.py` reads the render layer of the EXR with the most
channels (not a composite layer) and writes `combined`, `depth`, `normal`, `position`,
`diffuse_color`, `glossy_color`, `emit` and `uv` as float32 arrays, `object_index` as
int32 with `object_names` and `object_types` (the rows), and `size` (W, H); `normal` and
`position` are turned from Blender's axes to the description's, `(x, y, z) -> (x, z, -y)`
([surface](../internals/reference/surface.md)).

Cycles writes Z, Position and Object Index once, from the first sample, at the first
surface the camera ray meets (a later surface overwrites them while the ray passes
transparent ones), and adds Normal and UV at every sample from the first surface whose
alpha reaches the view layer's pass alpha threshold (0.5). A ray scattered by a volume
before any surface (a world volume) writes no Z there in that sample, while the Normal
of later samples is kept.

## Geometry keys and copies

`common.copies` walks the depsgraph's object instances of type MESH, CURVE, SURFACE,
FONT and META that Cycles' camera rays see (below), and skips those with no triangles;
an object whose evaluation gives no mesh counts no triangles and is listed by its type. A copy's base is the original object's
name when the object has a modifier or a shape key, or is not a mesh; otherwise it is the
mesh data's name. Its key is the base and a number k: the k-th distinct evaluated mesh
(by its address during the walk) met under that base. Copies of one evaluated mesh share
a key, also when geometry nodes instance it; one object whose geometry nodes emit several
meshes gives one key a mesh. No triangle count decides a key. Each key's mesh is taken at
its first copy, during the walk: a geometry-nodes instance is a temporary that the walk
reuses.

### What camera rays see

The scene is evaluated as the render evaluates it: before the walk, in that session only,
`common.render_visibility` sets what the viewport evaluates to the render's settings.

| setting | set to |
| --- | --- |
| object hidden in the viewport (`hide_viewport`, the eye) | `hide_render`; the eye opened |
| collection hidden in the viewport, a view layer's collection hidden (the eye) | the collection's `hide_render`; the eye opened |
| collection excluded from the view layer | kept: excluded from the render too |
| modifiers' viewport switch | their render switch |
| Subdivision Surface and Multiresolution levels | their render levels |
| an instancer shown (`show_instancer_for_viewport`) | `show_instancer_for_render` |
| particle settings: display amount, children, display method | 100 %, the render's children, as rendered |

Of the evaluated instances, `common.camera_rule` leaves out, each with its reason:

| left out | reason |
| --- | --- |
| the object or its instancer not visible to camera rays (`visible_camera`) | camera rays off |
| the object or its instancer a holdout (its own or its collection's) | holdout |
| in an indirect-only collection | indirect only |
| every material without a surface and with a volume | volume material |
| every material's surface a Transparent BSDF, a Principled BSDF of unlinked alpha 0, or an Add Shader of those with an Emission | fully transparent material |

Display types (bounds, wire) do not count: Cycles draws such objects as they are. A
shadow catcher is drawn. A material with an alpha above 0 is kept: Cycles' camera sees
it, and its passes come from it or from behind it as written above.

`not_exported.objects` lists, each as `{"name", "type", "reason"}`: objects of a type the
copies do not take (`type not copied`: hair curves, point clouds, volumes, grease
pencil), particle hair (`HAIR`, `hair strands not copied`), a world volume
(`WORLD`, `volume not copied`), the geometry left out above, an object with no mesh
(`no mesh`) and the objects of the view layer the render does not draw (`hidden in the
render`); at most 200, then one entry naming the count of the rest. The comparison gives
each listed object's pixels at the render camera from Cycles' Object Index.

`measure.py` counts the keys, the bases, the bases with more than one mesh, the stored
triangles (one mesh a key), the drawn triangles (every copy) and the copies, and records
beside them Blender's own scene statistics (its text and its triangle number), counted
without the keys. It also records objects by type, materials by what they use (a
Principled BSDF reaching the output, image textures on base colour, normal, roughness or
metallic, transmission, emission, volume, displacement), the geometry left out by reason
(`objects_left_out`), images and their sizes, lights
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
 "render": {"size": [W, H], "camera": "<name>", "shift": [x, y],
            "sensor_fit": "AUTO" | "HORIZONTAL" | "VERTICAL", "exposure": float,
            "view_transform": str, "look": str, "gamma": float},
 "world": {"color": [r, g, b], "strength": float, "environment": str | null,
           "rotation": [x, y, z]},
 "area_lights": [{"name": str, "shape": str, "size": [sx, sy], "color": [r, g, b],
                  "power": float, "matrix": [16 floats, row-major]}],
 "instances": {"file": "<stem>.instances.npz"},
 "materials": {"<name>": {"class": "P" | "S" | "X", "node": str (X only),
                "sockets": {"<input>": {"done": str, "node": str (lost only)}}}},
 "not_exported": {"materials": [str], "lights": [str],
                  "objects": [{"name": str, "type": str, "reason": str}],
                  "triangles": [{"node": str, "expected": int, "written": int}]}}
```

`size` is the render resolution times its percentage; the export scene takes the same
resolution and pixel aspect, so the file's `yfov` and `aspectRatio` are for that size.
`shift` is the camera's lens shift (Blender's `shift_x`, `shift_y`) in units of the side
its sensor fit names: positive x moves the view right (the optical axis lands left of the
picture's centre, `cx = W / 2 - shift_x W` for a horizontal fit), positive y moves it up
(`cy = H / 2 + shift_y H` rows from the top for a vertical fit, `H` replaced by `W` for a
horizontal one). `sensor_fit` is the camera's fit (`AUTO`, `HORIZONTAL`, `VERTICAL`);
Blender resolves `AUTO` at each size it renders, to `HORIZONTAL` when the width is at
least the height, else `VERTICAL`, and keeps the field of view of the side it names. The
file's `yfov` holds at its `aspectRatio` (the artist's size), so the fitted side's field
is recovered there and kept at the drawn size. The importer gives the render camera `shift_x`,
`shift_y` and `sensor_fit`; the reference's surface draws with them, and the scene's view
carries the shift as `shift` (x, y) in units of the longer side, the side of its `fov`
(the fit's side at the file's aspect converted), so the reference's raster and the card
draw with the principal point moved. The world is read when a
Background node feeds the output: its colour and strength. An Environment Texture on its
colour is copied beside the stem as `<stem>.world.<extension>`, with the rotation of a
Mapping node feeding it. Any other world gives its viewport colour, strength 1, and
`"world"` in `not_exported.objects`. An area light points along its local -Z; its matrix
is in glTF's axes and `power` is in watts. `not_exported.triangles` lists each node
whose mesh in the written `.glb` holds other than the triangles handed to the exporter
(read back from the `.glb`'s JSON chunk after writing). `materials` is the record of the
material rewrite (below); `not_exported.materials` names the materials of class X or with
an input `lost`. A material with a tiled (UDIM) image is written once per tile, named
`<name>.<tile>` in the `.glb`; its record is under `<name>`. The export's summary line gives the materials by class, those with a
loss, the seconds of the rewrite and its bakes.

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

## The materials

`materials.py` (with `graph.py`, `shaders.py` and `bake.py`) rewrites, in the built copy
only, every material of a copied mesh as a material output and one Principled BSDF fed by
constants and Image Texture nodes (with a UV Map or Texture Coordinate node, a Mapping,
a Separate Color or a Normal Map node), which the exporter writes as it is. The surface
shader is found from the active output's Surface through reroutes, muted nodes and
groups; groups are walked, not expanded (a socket inside a group is brought out through
a new output of each group on its path, in a copy, for a bake).

The class of a material:

| class | rule |
| --- | --- |
| P | the surface shader is a Principled BSDF |
| S | a tree of Diffuse, Glossy, Glass, Refraction, Transparent, Translucent, Emission, Mix Shader and Add Shader mapped by the table below onto one Principled BSDF |
| X | anything else: the Principled defaults with the material's viewport colour (`diffuse_color`) as the base colour; the node that stopped the mapping recorded |

Class S, a shader at a time (each input then follows the rows of P):

| shader | Principled inputs |
| --- | --- |
| Diffuse, Translucent | base colour = its colour, roughness 1, its normal, metallic 0 |
| Glossy alone | base colour = its colour, its roughness and normal, metallic 1 |
| Glass, Refraction | base colour = its colour, its roughness, IOR and normal, transmission 1 |
| Emission | base colour black, emission colour and strength = its own |
| Mix of a Diffuse and a Glossy | base colour = the diffuse's, roughness = the glossy's, metallic 0 when the factor is a Fresnel or Layer Weight node or the glossy's constant weight is under 0.5 (or an Add Shader); otherwise metallic 1 with the glossy's colour as base when that colour is tinted (linked, or channels more than 0.05 apart), else as the dielectric case; the normal is the diffuse's, else the glossy's |
| Mix with a Transparent | the other side's inputs, alpha = the factor (Transparent first) or 1 - the factor; MASK (cutoff 0.5) when the factor is an image's alpha or a threshold (Math greater, less, compare or round; a constant colour ramp), else BLEND |
| Mix or Add of a Principled BSDF and a Diffuse or Translucent | the Principled's inputs (the other lobe dropped) |
| Mix or Add with an Emission | the other side's inputs, the emission's colour and strength |
| Mix with a constant factor of 0 or 1 | the side it selects |

Class P, each input the exporter reads (base colour, metallic, roughness, alpha, emission
colour and strength, transmission weight, IOR, normal):

| what feeds it | done |
| --- | --- |
| nothing, or a chain whose value is one constant | `constant` |
| an Image Texture on uv coordinates (unlinked vector, UV Map, Texture Coordinate UV, through one Mapping of constant inputs), or one channel of it through a Separate Color in RGB mode; for the normal, a tangent-space Normal Map over such an image | `as_is`: the same nodes rebuilt |
| a chain of nodes that depend only on their inputs (mixes, colour ramps, hue and saturation, curves, maths, invert, gamma, brightness, clamp, map range, separate and combine, ...) over constants, Image Textures and procedural textures on uv coordinates, every leaf in one texture space (uv map and Mapping) | `baked` (below), the leaves' Mapping put in front of the baked image |
| a Bump node over such a chain (its own normal unlinked, strength and distance constant) | `bump`: the height baked and turned into a normal map |
| a chain with a node that depends on the geometry or the object (generated or object coordinates, a procedural texture off uv, geometry, layer weight, Fresnel, ambient occlusion, attributes, object info, light path, ...), leaves in different texture spaces, an image of several UDIM tiles under a bake (the quad covers tile 1001; reason `UDIM tiles`), a Bump over a normal map, or a non-constant chain on emission strength or IOR (the exporter writes those as constants) | `lost`: the constant is the mean of the chain baked on the quad (generated and object coordinates are the quad's) (a missing attribute is 0 there, as Cycles reads it) when no node in it depends on the ray or the view (light path, camera data, light falloff, particle, point and hair info), else the socket's own value; the normal is left unlinked |

A bake: a copy of the material whose surface is an Emission of the socket, on a unit
quad (uv = position, every uv map the chain names) in a scene of its own, baked by
Cycles (type EMIT, one sample, no margin) at the largest leaf image's size, at most 4,096
a side (8 x 8 without an image leaf), with the leaves' Mapping muted. A result whose
values lie within 1e-4 of each other becomes the input's constant. Otherwise a new packed
8-bit image: sRGB for base and emission colour (encoded with the standard transfer),
non-colour data for the others.

A Bump's height `h` over the uv square (W x H texels, rows from v = 0) gives, by central
differences repeating at the edges, `du = (h[x+1] - h[x-1]) W / 2`, `dv = (h[y+1] -
h[y-1]) H / 2`, the normal `n = normalize(-d du, -d dv, 1)` with `d` the node's distance
(negated when inverted), then `normalize(s n + (1 - s) (0, 0, 1))` with `s` its strength
(at least 0); stored as `n / 2 + 1 / 2` in a non-colour 8-bit image under a tangent-space
Normal Map of strength 1. The quad's uv square is one metre a side: on a mesh whose uv
density differs, Blender's Bump (which works in world units) bends the normal by another
amount.

The record gives, per material, its class and, per input, `as_is`, `baked`, `bump`,
`constant` or `lost` with the node type (or the reason) that caused a loss.

`selftest_materials.py` checks the rewrite on materials it makes in an empty file: a
Diffuse and a Glossy mixed by a Fresnel node, a Glossy alone, a Transparent mixed by an
image's alpha, a plain Principled, a base colour that is an Invert of a 4 x 4 image and a
colour ramp over one (the baked image against 1 - the image and the ramp of it, to 1 /
255 in the stored sRGB values; the image's values are Cycles' own, read by a bake of the
image alone, as Cycles' decoding of an 8-bit sRGB image differs from the standard
transfer by up to about one step), a Bump over an image (the normal map at four texels
against the formula above) and a Noise texture on object coordinates (`lost`).

## The same glTF as the truth

The renderer's input is the glTF file and its sidecar; what the file does not carry, the
renderer cannot draw. Its picture is therefore judged against Cycles reading the same
file, not against Cycles rendering the `.blend`.

`export --plain` writes the export's files with the materials as they are: Blender's own
glTF exporter decides what each material becomes, nothing is baked or rewritten, and the
sidecar's `materials` is empty. Without `--plain` the export is as above.

What the plain export can carry of a scene is read from the `.blend` itself, before any
export, by `scripts/blender/exportable.py` (run inside Blender on the artist's file):

```
blender --background <file.blend> --python scripts/blender/exportable.py -- OUT.json [--rays W H]
```

For each material the camera's rays or the drawn triangles reach, it records how the
exporter writes the Principled BSDF's base colour, roughness and metallic (`constant`,
`image`, `image_altered`: other nodes between the input and its image, dropped;
`attribute`; `lost`, written as white) and its normal (`normal_map`, `bump_as_normal`,
`lost`), whether the surface is a Principled at all (`mix_principled`, `other_bsdf`,
`emission`), its alpha, transmission and emission strength, and whether displacement or a
volume is linked; each material is weighted by its drawn triangles, its world area and
its share of the camera's picture (one ray a cell of a W x H grid, 160 x 90 by default).
The record also names the world as the sidecar sees it, the lights by type, what Cycles
draws and the export does not carry, missing images and libraries, and whether the
camera is animated. It is the per-material reason behind a scene's loss in
[the glTF truth](../performance/gltf_truth.md); no measurement page quotes its records.

`gltf_truth` runs `from_gltf.py`, then `render.py` on the `.blend` it saved, with the
engines, size and samples of `render`. `from_gltf.py` starts from an empty file and:

- reads `<stem>.glb` with Blender's glTF importer at its defaults;
- places each node of the instance table at its matrices (glTF's axes turned back to
  Blender's): a node with one copy gets that matrix, a node with more is hidden from the
  render and drawn by a geometry-nodes object of its own whose points carry the matrices
  (Instance on Points, then Set Instance Transform from a 4 x 4 point attribute);
- makes the sidecar's render camera the scene's camera, with the sidecar's sensor fit and
  lens shift, and its field of view recovered from the file's `yfov` at the sidecar's
  size: the vertical field for a vertical fit, the horizontal one for a horizontal fit,
  the larger of the two for `AUTO`;
- makes the world a Background of the sidecar's colour and strength, its environment map
  through a Mapping of the sidecar's rotation when there is one;
- adds the sidecar's area lights (shape, size, colour, power, matrix);
- sets the render size, the view transform, look, exposure and gamma of the sidecar, and
  OpenEXR's interleaved layout (one part holding every pass, as `planes.py` reads it).

Everything else is Blender's default in an empty file: Cycles' bounces, clamps and light
settings, EEVEE's settings, no compositor nodes, no depth of field (glTF has none). The punctual
lights go through the exporter's and the importer's unit conversions. `planes` reads
`truth_gltf.exr` and `light_compare.py passes` runs `light_passes.py` on
`scene_gltf.blend`, so the surface's and the light's comparisons read the same glTF as the
reference.

The card's picture is judged the same way: `python -m prism_cli open
$PRISM_DATA/artist/<KEY>/scene.glb --pipeline lit --size 1280 720 --bake none` draws the
plain export ([the command line](cli.md#open)), and its last picture is compared with
`truth_gltf.png`. Which scenes pass, what the plain export loses against the `.blend` and
how the reference and the card compare: [the glTF truth](../performance/gltf_truth.md),
from [measurements/gltf_truth](../../measurements/gltf_truth/README.md). A scene whose glTF
picture is not a coherent picture of the scene is left out as a test scene, not repaired.

The reference's own comparisons against Cycles' passes, both without a card:
`python scripts/run/surface_compare.py KEY [KEY ...] [--data FOLDER] [--size W H]
[--factor N]` (the surface's planes, [surface](../internals/reference/surface.md)) and
`python scripts/run/light_compare.py passes|compare|table [KEY ...] [--data FOLDER]
[--size W H] [--samples N] [--timeout SECONDS] [--runs ...]` (the direct light: `passes`
renders Cycles' direct-light passes in Blender, `compare` sets the reference's direct
light against them, writing the pictures and `compare.json` under
`<data>/artist/<key>/light/`; `table` gathers them into a README table).

## Not carried yet

- Material inputs the exporter does not read (coat, sheen, subsurface, specular tint and
  the like): the rebuilt Principled BSDF has their defaults.
- Area lights in the `.glb`: they are in the sidecar only.
- Hair curves, particle hair, point clouds, volumes, world volumes and grease pencil:
  listed in `not_exported.objects`, no geometry made for them.
- Animation, armatures and shape keys: the export is one frame, evaluated.
- The render's own evaluation is approached by the settings above; a geometry-nodes
  tree that asks whether it runs in the viewport still answers yes.
- Triangles the glTF exporter leaves out, each recorded in `not_exported.triangles`.
  Two cases were measured. When a mesh's material uses a tiled (UDIM) image, the
  exporter keeps a triangle only when its first corner lies on an existing tile. In the
  second case, one object lost part of its triangles, and the cause was not found.
