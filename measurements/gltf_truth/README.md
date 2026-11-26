# The glTF truth: Cycles reading the same file

Each scene of the artists' table whose `.blend` is on disk, exported plain
(`artist_scenes.py export --plain`: Blender's own glTF exporter, the instance table and the
sidecar, no material rewrite, no bake), then read back by Blender's glTF importer into an
empty file with the sidecar applied and rendered (`artist_scenes.py gltf_truth`,
[the same glTF as the truth](../../docs/guides/artist_scenes.md#the-same-gltf-as-the-truth)).
A scene is usable as a test scene when its glTF picture is a coherent picture of the scene:
materials present, lit, nothing white or black where the `.blend` has surface. No scene
was repaired.

- Blender 5.3.0; Cycles on one GPU (OptiX), 1,280 x 720, 256 samples, no denoiser; EEVEE
  at an empty file's settings. Date: 2026-11-27 (UTC+8). Exports and renders under 16 CPUs.
- Cycles(.blend): `render.py` on the artist's file, 1,280 x 720, 256 samples. Six scenes
  (classroom, italian_flat, charge_factory_floor, the_shed, hidden_alley, lynxsdesign) use
  the `truth.png` already rendered; the other twelve were rendered for this table with the
  camera's depth of field off. hidden_alley's and lynxsdesign's earlier `truth.png` were
  rendered before depth of field was turned off.
- PSNR on the displayed pictures (values 0 to 1); "far" is the share of pixels whose
  largest channel difference passes 0.1.
- An export past 300 s is stopped. Seconds are the export script's own.

## The scenes

| scene | drawn triangles | export s | PSNR Cycles(glTF) vs Cycles(.blend) | far | usable, or why not |
| --- | ---: | ---: | ---: | ---: | --- |
| eevee_archiviz | 211,392 | 0.5 | 11.46 | 0.57 | no: the window's glass has no Principled BSDF and is exported opaque; the room behind it is black |
| gaku | 1,187,500 | 3.3 | 7.15 | 0.99 | no: nearly every surface black or white; 42,408 triangles not written by the exporter |
| classroom | 1,252,126 | 2.1 | 13.00 | 0.83 | no: every material is exported as the default (75 materials, no image); the room is grey |
| red_autumn_forest | 3,337,993 | 18.4 | 8.35 | 0.91 | no: grass and trees white, the sky black |
| wanderer | 3,528,244 | 21.7 | 13.56 | 0.90 | no: the robot's paint white; the fog's volume lost |
| italian_flat | 4,821,520 | 104.0 | 15.69 | 0.59 | yes: a darker, glossier picture of the same room |
| splash_fox | 8,137,904 | 46.8 | 6.91 | 0.93 | no: the fox and the plants white |
| the_shed | 8,436,842 | 112.2 | 13.96 | 0.43 | no: Cycles' picture is black (mean 0.002): the sunlight through the door does not reach the floor, cause not established |
| hidden_alley | 8,994,697 | 107.0 | 12.78 | 0.61 | no: the ground white, the back wall pink and white; the fog lost |
| pine_forest | 10,640,915 | 65.6 | 8.55 | 0.86 | no: the trees are drawn as their low-polygon viewport proxies |
| overgrown | 11,214,200 | 111.9 | 9.11 | 0.91 | no: materials dark or white; the framing differs (the camera's lens is animated and the exporter read it at frame 1) |
| secret_deer | 13,105,532 | 39.8 | 11.10 | 0.51 | no: the plants white or black |
| lynxsdesign | 29,756,755 | 167.9 | 10.97 | 0.91 | yes: half as bright, the large painting's black and white swapped |
| charge_factory_floor | 37,728,911 | 85.7 | 14.36 | 0.61 | yes: the fog's volume lost, the rest coherent |
| gold | 44,623,554 | 133.4 | 5.99 | 0.91 | no: a grey surface (the water's) covers the view |
| sprite_fright | 90,999,302 | 78.6 | 6.95 | 0.81 | no: trees white, the ground black |
| namaqualand | 223,992,071 | 132.5 | 9.83 | 0.88 | no: the sky is lost; the picture is nearly black |
| scanlands | 358,959,541 | 18.3 | 9.24 | 0.94 | no: the sea white; the framing differs |
| charge | | stopped | | | the exporter stops: an image the file names is missing from the download |
| verdant_trail | | > 300 | | | the export was stopped at 300 s |

## The reference and the card against the same glTF

The usable scenes, with Cycles(glTF) as the truth. "Direct" is the reference's direct
light (`scripts/run/light_compare.py compare`) against Cycles' passes of the same `.blend`
made from the glTF with no bounce, both displayed by the reference; "card" is
`python -m prism_cli open scene.glb --pipeline lit --size 1280 720 --bake none` on card 1
(16 frames, the last) against Cycles(glTF) with its bounces.

| scene | registered pixels | base colour MAD | diffuse, ratio of means | glossy, ratio of means | PSNR direct | PSNR card |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| italian_flat | 0.988 | 0.155 | 1.08 | 0.54 | 16.82 | 11.91 |
| lynxsdesign | 1.000 | 0.204 | 1.12 | 0.57 | 16.84 | 14.14 |
| charge_factory_floor | 1.000 | 0.512 | 1.38 | 0.84 | 15.95 | refused: 73 lamps, the light table holds 32 |

What makes the differences:

- The material model. Sheen and clearcoat are dropped: a fabric with `KHR_materials_sheen`
  is near white in Cycles' diffuse colour and its plain texture in ours (italian_flat's
  sofas); charge_factory_floor's dominant material carries sheen and clearcoat, which
  Cycles' colour passes count and the reference's base colour does not (the 0.512).
  Glossy light is about half of Cycles' on the two interiors.
- Shadows. Masked, blended and transmitting surfaces cast opaque shadows: italian_flat's
  sun, behind glass, gives 0 against Cycles' light.
- Emission. Emitting surfaces are not drawn in the reference's direct light (the window's
  backdrop and the poster are black in ours, lit in Cycles').
- The world. lynxsdesign's map is an `.exr`, which the reference does not read: its world
  light is 0.
- The card's lighting is the converter's (an environment of its own, a constant ambient;
  area lights and the sidecar's world dropped), so its picture is brighter and flatter.
  lynxsdesign shows square blocks of wrong colour over the staircase and ceiling, and a
  moire on the armchairs' fabric (the filtering).
- Tone. Filmic and AgX with their looks are not applied: the standard sRGB transfer.
- Settings of the comparison: Cycles(glTF) runs at an empty file's light settings, not
  the artist's; lens shift is not applied by the reference's camera.
