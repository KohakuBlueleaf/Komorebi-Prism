# The glTF truth: another renderer reading the same file

A glTF file goes in, a frame comes out; its truth is another renderer reading the same
file. Each scene of the artists' table is exported plain (Blender's own glTF exporter,
no material rewrite, no bake), read back by Blender's glTF importer and rendered by
Cycles, and that picture is compared with Cycles on the artist's `.blend` (what the
export loses) and with the reference and the card on the same glTF (what the renderer
does). How the pictures are made is
[the same glTF as the truth](../guides/artist_scenes.md#the-same-gltf-as-the-truth);
every number is from [measurements/gltf_truth](../../measurements/gltf_truth/README.md).

Conditions: Blender 5.3.0, Cycles on one GPU (OptiX), 1,280 x 720, 256 samples, no
denoiser, 2026-11-27 (UTC+8). PSNR on the displayed pictures (values 0 to 1); "far" the
share of pixels whose largest channel difference passes 0.1. No scene was repaired.

## What the export keeps

A scene is usable when its glTF picture is a coherent picture of the scene: materials
present, lit, nothing white or black where the `.blend` has surface. Three of eighteen
exported scenes are:

| scene | drawn triangles | PSNR Cycles(glTF) vs Cycles(.blend) | far | |
|---|---:|---:|---:|---|
| italian_flat | 4,821,520 | 15.69 | 0.59 | a darker, glossier picture of the same room |
| lynxsdesign | 29,756,755 | 10.97 | 0.91 | half as bright, the large painting's black and white swapped |
| charge_factory_floor | 37,728,911 | 14.36 | 0.61 | the fog's volume lost, the rest coherent |

The others lose their materials to the exporter (surfaces white or black, every material
the default, glass exported opaque), their sky, their framing (an animated lens read at
frame 1) or their geometry (viewport proxies, triangles not written); two did not export
(a missing image, past 300 s). Each scene's reason is in the measurement's table. Those
scenes are left out as test scenes.

## The reference and the card against the same glTF

Cycles(glTF) with its bounces is the truth. "Direct": the reference's direct light
against Cycles' passes of the same scene with no bounce; "card": `python -m prism_cli open
scene.glb --pipeline lit --size 1280 720 --bake none` on card 1, the last of 16 frames.

| scene | base colour MAD | diffuse, ratio of means | glossy, ratio of means | PSNR direct | PSNR card |
|---|---:|---:|---:|---:|---:|
| italian_flat | 0.155 | 1.08 | 0.54 | 16.82 | 11.91 |
| lynxsdesign | 0.204 | 1.12 | 0.57 | 16.84 | 14.14 |
| charge_factory_floor | 0.512 | 1.38 | 0.84 | 15.95 | refused: 73 lamps, the light table holds 32 |

What makes the differences:

- **The material model.** Sheen and clearcoat are dropped; glossy light is about half of
  Cycles' on the two interiors.
- **Shadows.** Masked, blended and transmitting surfaces cast opaque shadows (italian_flat's
  sun, behind glass, gives 0).
- **Emission.** Emitting surfaces are not drawn in the reference's direct light.
- **The world.** An `.exr` map is not read: lynxsdesign's world light is 0.
- **The card's lighting** is the converter's (an environment of its own, a constant
  ambient; area lights and the sidecar's world dropped), so its picture is brighter and
  flatter; lynxsdesign shows square blocks of wrong colour over the staircase and ceiling
  and a moire on the armchairs' fabric.
- **Tone.** Filmic and AgX are not applied: the standard sRGB transfer.
- **The comparison.** Cycles(glTF) runs at an empty file's light settings; lens shift is
  not applied by the reference's camera.
