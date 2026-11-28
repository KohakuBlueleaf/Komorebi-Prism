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

The usable scenes, with Cycles(glTF) as the truth (`scripts/run/compare.py SCENE --pipeline
gi_threads --frames 16 --crop all`, 2026-11-28, main at f614f61, the card at link 16 GT/s).
"Direct" is the reference's direct light against Cycles' passes of the scene made from
the glTF with no bounce, the passes lit by the file's own lights; "reference" the
reference's whole frame; "card" `gi_threads` on card 0 with the far field built,
1,280 x 720, the last of 48 frames, against Cycles(glTF) with its bounces (italian_flat
12, lynxsdesign 12). PSNR against the truth displayed by the standard sRGB transfer, and
against Blender's own display (its view transform and look).

| scene | registered pixels | base colour MAD | diffuse, ratio of means | glossy, ratio of means | specular, ratio of means | PSNR direct | PSNR reference | PSNR card | PSNR card, Blender's display |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| italian_flat | 0.988 | 0.185 | 0.94 | 0.80 | 0.63 | 21.07 | 15.97 | 15.29 | 14.51 (Filmic, High Contrast) |
| lynxsdesign | 1.000 | 0.126 | 1.07 | 0.66 | 0.78 | 16.59 | 12.48 | 12.48 | 18.03 (AgX, AgX - Punchy) |
| charge_factory_floor | | | | | | | | refused: 73 lamps, the light table holds 32 | |

- Cycles(glTF): 43.4 s (italian_flat) and 40.4 s (lynxsdesign) for 256 samples on one
  V100-class GPU.
- The whole frame's ratio of means, card over truth: italian_flat 1.21, lynxsdesign 0.38.
- The reference's frame and the card draw the converter's lighting; the passes the
  file's. Neither scene's sidecar has view tables, so the card draws with the standard
  sRGB transfer.
- italian_flat's 1,280 x 720 card picture uses the scene's exposure (2.17, the sidecar's
  `render.exposure`); lynxsdesign's is 1.
