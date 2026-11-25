# The preset `lit`: a lit frame and the sun's pass, as thread commands

The raster stage's passes for every layer, SHADE's lit form for every layer, LIGHT (twice
with a glass layer), SHOW and the push, run by the director's FRAME command; the sun's
shadow map by the thread command `sun` of `direct.shadow_pcf` (a DEPTH view a quadrant,
through the same units), sent by the loop before the frame when the sun moves.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz as the runs report it,
  its link to the host at 16 GT/s.
- Date: 2026-11-26 (UTC+8), Komorebi at b5589ff78; every
  record from one build of the tree.
- Each case: 1,024 x 1,024 (and the lit frame at 1,280 x 720 and 1,920 x 1,080, below),
  16 frames, the times the medians of the times rows in ms.
  The lit and sun records are the light stage's check (`check/thread_frame.check`) run
  by `prism.check.harness` on a Loop of the preset, the scene's materials, name and
  lights given: `scripts/run/preset.py --pipeline lit --check
  prism.stages.direct.light.check.thread_frame.check --scene S --view overview --size 1024
  1024 --card 1`, and for `sun` the same with `--option "sun=(120.0, 40.0)"` (the sun at
  azimuth 120, elevation 40 in the options). The controls are `scripts/run/preset.py
  --pipeline lit --scene S --view overview --size 1024 1024 --card 1 --set NAME=VALUE`,
  one control a run.
- Pass: the pictures of frames 1 and 16 against `prism_reference`'s lit frame at that
  setting (`stages/direct/light/model/expect.light_check`; at a moved sun the
  reference's moved lights with the shadow map rebuilt): the shares of pixels over 2 / 4 /
  8 of 255 apart and the largest error, as recorded; the sun's map against the reference's
  (`sun_check`): 0 texels apart, 0 empty on one side; frames 1 and 16 the same picture;
  every code 0.

## What is here

| file | holds |
| --- | --- |
| `<scene>_overview_1024_1024_lit.json` | the harness record at the lights' own sun: codes, layers, tone, terms, each checked picture's report, whether frames 1 and 16 match, the last row's sequence, the parts' medians by layer (`part` the first layer's, `part.<i>` layer i's) |
| `<scene>_overview_1024_1024_sun.json` | the same at the sun (120, 40), with the sun's map report, the `sun` command's code and its times (`sun_times`: the pass and each quadrant's, us) |
| `<scene>_overview_<W>_<H>_lit.json` | the lit record at 1,280 x 720 and 1,920 x 1,080, as `*_1024_1024_lit.json` |
| `controls/<sun, tone, term>/<scene>_overview_1024_1024.json` | the preset runner's record with one control set: `direct.shadow_pcf.sun=(120.0, 40.0)`, `direct.light.exposure=1.5`, `direct.light.term_shadow=False` |

## Pictures

The shares over 2 / 4 / 8 of 255 and the largest error, frame 1 (frame 16 the same in
every case).

| scene | lit | sun (120, 40) | sun's map: texels apart / one side empty |
| --- | --- | --- | --- |
| sponza | 0.000459 / 0.000175 / 0.000106, 75 | 0.000441 / 0.000141 / 3.9e-05, 77 | 0 / 0 of 4,194,304 |
| bistro_interior | 6.6e-05 / 2.7e-05 / 5e-06, 13 | 6.1e-05 / 2.8e-05 / 7e-06, 13 | 0 / 0 |
| bistro_exterior | 0.004281 / 0.000659 / 0.000262, 109 | 0.001556 / 0.000506 / 0.000154, 111 | 0 / 0 |

The controls, one a run, against the reference at that setting:

| scene | sun moved | exposure 1.5 | shadow term off |
| --- | --- | --- | --- |
| sponza | 0.000441 / 0.000141 / 3.9e-05, 77 | 0.000573 / 0.000206 / 0.000115, 81 | 5e-06 / 3e-06 / 2e-06, 13 |
| bistro_interior | 6.1e-05 / 2.8e-05 / 7e-06, 13 | 8.8e-05 / 3.4e-05 / 1e-05, 15 | 7.5e-05 / 3.1e-05 / 1.1e-05, 22 |
| bistro_exterior | 0.001556 / 0.000506 / 0.000154, 111 | 0.005873 / 0.000991 / 0.000284, 117 | 1.5e-05 / 8e-06 / 2e-06, 11 |

## Times

Reported, not tuned. In ms. A layer's "raster" is its eight passes summed (COUNT, SUM,
HIST, HSUM, middle, PLACE, SETUP, FILL); SHADE the layer's lit form.

| scene | layer | raster | SHADE |
| --- | --- | --- | --- |
| sponza | opaque | 3.606 | 3.376 |
| sponza | masked | 1.451 | 0.782 |
| bistro_interior | opaque | 5.601 | 3.653 |
| bistro_interior | masked | 1.207 | 0.299 |
| bistro_interior | glass | 2.260 | 0.709 |
| bistro_exterior | opaque | 8.603 | 5.738 |
| bistro_exterior | masked | 5.638 | 2.372 |
| bistro_exterior | glass | 1.194 | 0.763 |

The frame: raster over every layer, SHADE every layer, LIGHT with its glass form (the
glass form's part apart), SHOW, PUSH.

| scene | frame | raster | SHADE | LIGHT | LIGHT glass | SHOW | PUSH |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sponza | 12.050 | 5.057 | 4.158 | 1.748 | - | 0.798 | 0.288 |
| bistro_interior | 18.136 | 9.068 | 4.661 | 3.262 | 0.890 | 0.863 | 0.287 |
| bistro_exterior | 27.947 | 15.435 | 8.873 | 2.544 | 0.971 | 0.797 | 0.288 |

At the sun (120, 40) (`*_sun.json`): the frame, and the `sun` command that made the map
before the first frame (the first pass of the run, every unit set up before it), in ms,
its four quadrants apart.

| scene | frame | sun pass | quadrants |
| --- | --- | --- | --- |
| sponza | 12.080 | 19.18 | 4.98 / 4.63 / 4.76 / 4.80 |
| bistro_interior | 18.108 | 32.85 | 11.10 / 8.46 / 7.33 / 5.96 |
| bistro_exterior | 27.913 | 56.80 | 13.69 / 15.79 / 16.27 / 11.04 |

A small layer (sponza's and bistro_interior's masked, bistro_exterior's glass) costs 1.19
to 1.45 ms of raster, about half of it the middle pass, as in the preset `textured`
(`measurements/textured_frame/`).

## At 1,280 x 720 and 1,920 x 1,080

The lit frame at the lights' own sun, each case
`scripts/run/preset.py --pipeline lit --check prism.stages.direct.light.check.thread_frame.check
--scene S --view overview --size W H --card 1`, 16 frames, the build of the records at
1,024 x 1,024, card 1 (link 16 GT/s), AICLK 1,350 MHz before and after, 2026-11-26
(UTC+8); every code 0, frames 1 and 16 the same picture. These runs record the card's
times only, not the host's frame.

Frame 1's shares over 2 / 4 / 8 of 255 and the largest error:

| scene | size | lit |
| --- | --- | --- |
| sponza | 1280x720 | 0.000521 / 0.000185 / 0.000106, 73 |
| bistro_interior | 1280x720 | 6.7e-05 / 2e-05 / 5e-06, 12 |
| bistro_exterior | 1280x720 | 0.00458 / 0.000723 / 0.000254, 118 |
| sponza | 1920x1080 | 0.000518 / 0.000186 / 9.8e-05, 85 |
| bistro_interior | 1920x1080 | 7.6e-05 / 2.5e-05 / 5e-06, 30 |
| bistro_exterior | 1920x1080 | 0.004608 / 0.000694 / 0.000235, 100 |

The frame and its parts, as the table at 1,024 x 1,024 above:

| scene | size | frame | raster | SHADE | LIGHT | LIGHT glass | SHOW | PUSH |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sponza | 1280x720 | 10.882 | 4.789 | 3.614 | 1.504 | - | 0.709 | 0.259 |
| bistro_interior | 1280x720 | 18.342 | 9.560 | 4.749 | 2.981 | 0.827 | 0.788 | 0.259 |
| bistro_exterior | 1280x720 | 26.116 | 14.756 | 7.960 | 2.467 | 1.054 | 0.715 | 0.258 |
| sponza | 1920x1080 | 18.952 | 7.682 | 6.062 | 3.099 | - | 1.542 | 0.565 |
| bistro_interior | 1920x1080 | 28.914 | 13.386 | 7.630 | 5.787 | 1.529 | 1.540 | 0.565 |
| bistro_exterior | 1920x1080 | 38.958 | 19.250 | 12.580 | 4.995 | 2.118 | 1.547 | 0.565 |

A layer's raster (its eight passes):

| scene | size | opaque | masked | glass |
| --- | --- | --- | --- | --- |
| sponza | 1280x720 | 3.445 | 1.345 | - |
| bistro_interior | 1280x720 | 6.018 | 1.178 | 2.365 |
| bistro_exterior | 1280x720 | 8.478 | 5.138 | 1.141 |
| sponza | 1920x1080 | 5.542 | 2.139 | - |
| bistro_interior | 1920x1080 | 8.126 | 1.942 | 3.317 |
| bistro_exterior | 1920x1080 | 11.219 | 6.165 | 1.866 |
