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

Cycles(glTF) with its bounces is the truth (`scripts/run/compare.py`, 2026-11-28, main at
f614f61). "Direct": the reference's direct light against Cycles' passes of the same scene
with no bounce; "reference": the reference's whole frame; "card": `gi_threads` on the card
with the far field built, 1,280 x 720, the last of 48 frames. PSNR on the truth displayed
by the standard sRGB transfer.

| scene | registered pixels | base colour MAD | diffuse, ratio of means | glossy, ratio of means | PSNR direct | PSNR reference | PSNR card |
|---|---:|---:|---:|---:|---:|---:|---:|
| italian_flat | 0.988 | 0.185 | 0.94 | 0.80 | 21.07 | 15.97 | 15.29 |
| lynxsdesign | 1.000 | 0.126 | 1.07 | 0.66 | 16.59 | 12.48 | 12.48 |
| charge_factory_floor | | | | | | | refused: 73 lamps, the light table holds 32 |

Cycles takes 43.4 s (italian_flat) and 40.4 s (lynxsdesign) for its 256 samples on one
V100-class GPU; the card's frame at 1,920 x 1,080 is 29.68 and 37.75 ms standing
([gi_threads](gi_threads.md)).

What makes the differences:

- **The lights.** The reference's frame and the card draw the converter's lighting (an
  environment of its own, a constant ambient); the file's own lights are drawn only with
  the option `file_lights` ([glTF scenes](../guides/gltf_scenes.md#the-files-own-lighting-file_lights)).
  Cycles' passes use the file's. lynxsdesign's picture on the card is darker than Cycles'
  (ratio of means 0.38), without the ceiling's cove light.
- **The card against the reference.** On lynxsdesign the two whole frames give the same
  PSNR (12.48); on italian_flat the card's is 0.68 dB lower.
- **Tone.** The card applies Filmic or AgX only when the scene's sidecar has its view
  tables; neither scene has them, so both use the standard sRGB transfer. Against
  Blender's own display (Filmic High Contrast, AgX Punchy) the card's PSNR is 14.51
  (italian_flat) and 18.03 (lynxsdesign).
- **The comparison.** Cycles(glTF) runs at an empty file's light settings, not the
  artist's.
