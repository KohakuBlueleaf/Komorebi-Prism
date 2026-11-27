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
light, and gives the passes below.

When the scene is an opened scene of the data root (given by name, or a file whose key is
an opened scene's), the reference's whole picture is the preset's own reference frame
(`scripts/run/compare_frame.py`): `prism_reference.direct.frame.rasterize_lighted` with
the preset's terms, the scene's lighting file and the option `bounces`, the picture the
card's frames are checked against, with the term indirect when the scene has its far
field. It lights the scene as the card does (the converter's lights), not with the
sidecar's. `--no-reference` leaves both out.

## The indirect pass

The incumbent indirect light is split one way for everyone, as Cycles splits it: its
`diffuse_indirect` holds the light that has bounced at least once and no first-hit light
of the world, which is in `diffuse_direct`. The reference frame's term indirect is the
field's lookup, and the field holds the bounce passes plus each element's own sky
irradiance (`indirect.light.field_source`), with the lights' ambient where no voxel has
data. `compare_frame.bounces_only` makes the field of the bounce passes alone
(`element_light`'s passes, summed, through `field_values`) and no ambient, and the frame is
drawn again with it. Then, in linear colour:

- bounces = that frame less the frame without the terms indirect, sky and ambient;
- the sky's own light = the frame less that frame; it goes with the direct light: the
  pass `frame_direct` (the frame's sun and lamps plus the sky's own light, with the
  albedo) is judged against `diffuse_direct` x `diffuse_color`;
- the reference's indirect pass is the bounces, against `diffuse_indirect` x
  `diffuse_color`, over the registered pixels.

The card draws `--frames` frames for the whole picture, then (`compare_card.py --plain`)
sets the light unit's tone to the plain curve, saturation 1, and the display's transfer to
the power at gamma 2.2 (no view transform), and draws them again for the passes (the file's
view transform stays on the whole picture only), then turns its control
`<light unit>.indirect` off and draws them once more (`--off indirect`). Each pass picture
is turned back into linear colour (the 1/2.2 power and x / (1 + x) undone, over the
exposure; a clipped value is held at 254.5 / 255), and the card's pass is on less off,
plus the sky and ambient terms the switch put in (the reference's frame without indirect
less the frame without the three), less the sky's own light: the bounces as the card makes
them. `--card-from FOLDER` takes the card's pictures and record of an earlier run instead
of drawing.

Which lights lit each side is written in `numbers.json` (`lights`: the reference frame and
the card are lit by the converter's lighting file, the described passes by the file's).
The indirect pass judges the transport only when both sides are lit by the file's lights;
with the converter's, the light it starts from differs too (see `frame_direct`).

## The card

`--card C` draws the scene on card `C` with the preset `--pipeline` (`gi_threads` by
default) for `--frames` frames and takes the last picture. When the file is the source of
an opened scene of the data root (the same key), that scene is drawn by its name, with its
far field when its files are there (`scripts/run/compare_card.py`). Any other file is
opened by `python -m prism_cli open` into `<cache>/card_data` as its data root, with
`--bake` (`none` by default: the lights' visibility open, no bake), and has no far field.
With `$PRISM_DEVLOCK` set the run is wrapped as
`$PRISM_DEVLOCK --wait 3600 C -- timeout S ...`, and with `$PRISM_CARDRUN` set too, as
`$PRISM_DEVLOCK --wait 3600 C -- $PRISM_CARDRUN C -- timeout S ...` (a wrapper run inside
the lock, given the card's number; the command's output stays on its standard output). The preset lights the scene its own way
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
| `specular` | `specular` | `glossy_direct` x `glossy_color` | registered |
| `direct` | the direct picture | the direct passes times their colours, emission, world | registered |
| `indirect` | the bounces (above); the card's on less off, less the sky's own light | `diffuse_indirect` x `diffuse_color` | registered |
| `frame_direct` | the frame's sun, lamps and sky's own light, with the albedo | `diffuse_direct` x `diffuse_color` | registered |
| `whole` | the reference frame (else the direct picture), the card, `--add` | `combined` | all |

A scene's `normalTexture` may hold an image that is not a tangent-space normal map. Blender's
glTF exporter (the plain export) writes the first image upstream of the Normal input, also
through a Bump node, so a height image or even a colour image lands there: on italian_flat
31 of the 41 normal textures (43 % of the picture's pixels), on lynxsdesign 7 of 26
(28 %). The rewritten export bakes a Bump's height into a normal map, with the slope taken
a texture repeat rather than a metre: on lynxsdesign's fabric sofa and armchair its
vectors lie nearly in the surface (24 % of the pixels). Cycles reads the same image through
a Normal Map node, so the truth is drawn with the same normals, averaged over its samples a
pixel; one shading point a pixel is not. On such materials the light passes judge the
normals' handling of a broken input as much as the light: read them per material
(`numbers.json` has none; the analysis is by hand) before taking a ratio as the model's.

`glossy` is the specular lobe's light over the lobe's directional albedo, as Cycles'
glossy light is its glossy radiance over its glossy colour; `specular` is the lobe's
light itself against Cycles' glossy radiance, the comparison that holds whatever each
side divides by. For each pass: `ratio`, the mean of ours over the truth's (linear values, channel mean);
`psnr` and `far` (the share of pixels whose largest channel differs by more than 0.1) on
the display values in 0 to 1; `base_colour` also `mad`, the mean absolute difference of
the linear values a channel. The light passes are displayed with the sidecar's exposure
and the standard sRGB transfer, the base colour by the transfer alone. The whole picture
of each column is compared over every pixel with the truth displayed the same way (its
`ratio` from the display values decoded by the transfer); the card's picture also against
Blender's own display (`card_vs_blender_display`: the view transform and look applied).

## The pictures

- `strip.png`: one row a pass. The first row is the whole picture: the truth, the
  reference (its frame when it has one), the card and the `--add` pictures, then the
  difference of each against the truth; then the indirect pass (truth, reference, card,
  differences) when it was made; then base colour, diffuse, glossy, specular and direct
  (truth, reference, difference);
- `pass_<name>.png`: each pass's row alone (`pass_frame_direct.png` too);
- `crop_<name>.png`: the strip's columns cut to a crop and scaled up by a whole factor;
- `truth.png`, `truth_blender.png`, `reference.png` (the whole row's),
  `reference_direct.png`, `reference_frame.png`, the card's pictures (whole, `_plain`, `_off`);
- `numbers.json`, also printed as one JSON line.

A difference is the largest channel difference of the display values, blue at 0, red
at 0.3 or more.

## Crops

`scripts/run/compare_crops.py` names crops of a scene's view, by the file's stem and the
camera, as fractions `(x0, y0, x1, y1)` of the picture, so the same region is asked for at
any size. `--crop NAME` takes a named one, `--crop all` every one of the view,
`--crop NAME=x0,y0,x1,y1` one given here. Each crop's numbers are the whole picture's,
inside the crop.
