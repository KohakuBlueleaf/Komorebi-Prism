# Comparing a picture with Cycles on the same glTF

A picture of the renderer is judged against Cycles reading the same glTF file
([the same glTF as the truth](artist_scenes.md#the-same-gltf-as-the-truth)). One command
puts the three pictures of a view side by side and gives their numbers: the truth,
the reference's picture and, when asked, a card's.

```
python scripts/run/compare.py SCENE --out FOLDER [--size W H] [--samples N]
    [--camera NODE] [--crop NAME ... | all | NAME=x0,y0,x1,y1] [--no-reference]
    [--add LABEL=PICTURE.png ...]
    [--card C [--pipeline P] [--frames N] [--bake none|wait] [--card-timeout S]]
    [--gpu G] [--cache FOLDER] [--timeout S] [--data FOLDER]
```

`SCENE` is a `.glb` with its sidecar (`<stem>.prism.json` and its instance table) beside
it, as `artist_scenes.py export --plain` writes them, or the name of an opened scene of
the data root, whose entry names its source file. The size is 1,280 x 720 by default,
the samples 256, the camera the sidecar's render camera. Everything is written under
`--out` and the truths' cache; nothing under the data root or the repository.

## The truth

The truth is made once for a file, a camera, a size and a sample count, and kept:
`<cache>/<stem>_<10 hex digits>/truth_<camera>_<W>x<H>_s<samples>.npz` with Blender's
own picture (`.png`) and the render's record (`.json`); the digits begin the file's key,
the digest `prism_cli open` gives the file (its bytes, its sidecar's and its instance
table's). The cache is `--cache`, else `$PRISM_COMPARE_CACHE`, else `<out>/truth`. A
truth already kept is read, not rendered again.

To make it, `from_gltf.py` reads the file into an empty Blender file (once a key; the
`scene_gltf.blend` that `artist_scenes.py gltf_truth` left beside the file is used when
it is newer than the file's own files), and `scripts/blender/compare_truth.py` renders it
with Cycles: OptiX, the given samples, seed 0, no adaptive sampling, no denoiser, the light
settings of an empty file (12 bounces). It writes the passes as float32 planes:
`combined`; `diffuse_`, `glossy_` and `transmission_` `direct`, `indirect` and `color`;
`emit`, `environment`; `depth`, `position` and `normal` (in the description's axes, +Y
up). Blender is `$PRISM_BLENDER`, else `blender`; `--gpu G` gives it
`CUDA_VISIBLE_DEVICES=G`. `--camera NODE` names another camera node of the file; its field
of view is recovered as `from_gltf.py` recovers the render camera's, without shift.

Cycles' light passes are the light before the surface's colour: its combined picture is
the sum over the three lobes of (direct + indirect) times colour, plus emission and the
world.

## The reference

The reference's picture is the direct light of the described scene
(`prism_reference.direct.described`), as `light_compare.py` makes it: the surface planes
of the camera's view, one shadow ray a punctual light, fixed points on each area light,
fixed directions of the world. It reads the glTF's lights and the sidecar's area lights
and world, in radiometric units, so it stands beside Cycles' light. It has no indirect
light. `--no-reference` leaves it out.

## The card

`--card C` draws the scene on card `C` with the preset `--pipeline` (`gi_threads` by
default) for `--frames` frames and takes the last picture. When the file is the source of
an opened scene of the data root (the same key), that scene is drawn by its name, with its
far field when its files are there (`scripts/run/compare_card.py`). Any other file is
opened by `python -m prism_cli open` into `<cache>/card_data` as its data root, with
`--bake` (`none` by default: the lights' visibility open, no bake), and has no far field.
With `$PRISM_DEVLOCK` set the run is wrapped as
`$PRISM_DEVLOCK --wait 3600 C -- timeout S ...`. The preset lights the scene its own way
(the lighting file the conversion makes), not with the sidecar's lights.

## Pictures made elsewhere

`--add LABEL=PICTURE.png` adds a picture already made (by another preset, another run,
another renderer) as a column of its own, judged as the card's picture is: the whole
picture, its crops and the strip. Its size must be the truth's.

## The numbers

Pixels are registered when both sides see a surface and their positions lie within 1e-3
of the scene's diagonal (the rule of `surface_compare.py`).

| pass | reference | truth | pixels |
| --- | --- | --- | --- |
| `base_colour` | the surface's base colour | diffuse colour + glossy colour | registered, metallic under 0.01 |
| `diffuse` | `diffuse_light` | `diffuse_direct` | registered |
| `glossy` | `glossy_light` | `glossy_direct` | registered |
| `direct` | the direct picture | the direct passes times their colours, emission, world | registered |
| `whole` | the direct picture | `combined` | all |

For each pass: `ratio`, the mean of ours over the truth's (linear values, channel mean);
`psnr` and `far` (the share of pixels whose largest channel differs by more than 0.1) on
the display values in 0 to 1; `base_colour` also `mad`, the mean absolute difference of
the linear values a channel. The light passes are displayed with the sidecar's exposure
and the standard sRGB transfer, the base colour by the transfer alone. The whole picture
of each column is compared over every pixel with the truth displayed the same way (its
`ratio` from the display values decoded by the transfer); the card's picture also against
Blender's own display (`card_vs_blender_display`: the view transform and look applied).

## The pictures

- `strip.png`: truth, reference, card, then the difference of each against the truth;
- `pass_<name>.png`: truth, reference and their difference for each pass;
- `crop_<name>.png`: the strip's columns cut to a crop and scaled up by a whole factor;
- `truth.png`, `truth_blender.png`, `reference.png` and the card's picture;
- `numbers.json`, also printed as one JSON line.

A difference is the largest channel difference of the display values, blue at 0, red
at 0.3 or more.

## Crops

`scripts/run/compare_crops.py` names crops of a scene's view, by the file's stem and the
camera, as fractions `(x0, y0, x1, y1)` of the picture, so the same region is asked for at
any size. `--crop NAME` takes a named one, `--crop all` every one of the view,
`--crop NAME=x0,y0,x1,y1` one given here. Each crop's numbers are the whole picture's,
inside the crop.
