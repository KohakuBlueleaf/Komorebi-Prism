# The frame's time on the card

This repository's presets (`configs/pipeline/`), each on one Blackhole P150A at AICLK
1,350 MHz: card 1 with its link to the host at 16 GT/s, 2026-11-26 (UTC+8), Komorebi at b5589ff78.
Every number is copied from the records of the folder named under its table,
where the folder's README gives every part of the frame; a number taken from a record's
JSON is rounded as the folder's README rounds its own.

How to read a row: the scene and size; the row's picture check (each side's numbers
against `prism_reference`, as the folder says); the card frame, the median of the
frame's times rows in ms (the director's whole FRAME command, with the display and the
push where the preset has them); the host's frame and fps where a run recorded them,
with the host's load average over one minute at its start.

## raster: vertex colours

| scene | size | pixels differ (frames 1 / 100 / 200) | card frame | host frame | fps | load |
| --- | --- | --- | --- | --- | --- | --- |
| sponza_overview | 1024x1024 | 0 / 0 / 0 | 4.962 | 5.885 | 169.9 | 2.23 |
| bistro_interior_overview | 1024x1024 | 0 / 0 / 0 | 7.984 | 8.866 | 112.8 | 2.11 |
| bistro_exterior_overview | 1024x1024 | 0 / 0 / 0 | 13.340 | 14.265 | 70.1 | 2.07 |
| sponza_overview | 1280x720 | 0 / 0 / 0 | 4.673 | 5.455 | 183.3 | 2.39 |
| bistro_interior_overview | 1280x720 | 0 / 0 / 0 | 8.234 | 9.033 | 110.7 | 2.60 |
| bistro_exterior_overview | 1280x720 | 0 / 0 / 0 | 12.513 | 13.396 | 74.6 | 1.68 |
| sponza_overview | 1920x1080 | 0 / 0 / 0 | 7.813 | 9.543 | 104.8 | 1.92 |
| bistro_interior_overview | 1920x1080 | 0 / 0 / 0 | 11.570 | 13.042 | 76.7 | 2.70 |
| bistro_exterior_overview | 1920x1080 | 0 / 0 / 0 | 16.740 | 18.313 | 54.6 | 1.33 |

[measurements/raster_show/README.md](../../measurements/raster_show/README.md): the preset
`raster` with its display, 200 frames on a moving camera, `python -m prism_cli run
--pipeline raster --scene S --view overview --size W H --frames 200 --path forward
--check 0 99 199 --pictures --card 1`.

## textured: SHADE

| scene | size | pixels differ / largest error | card frame |
| --- | --- | --- | --- |
| sponza_overview | 1024x1024 | 8 / 16 | 10.781 |
| bistro_interior_overview | 1024x1024 | 62 / 21 | 15.442 |
| bistro_exterior_overview | 1024x1024 | 3 / 11 | 27.688 |

[measurements/textured_show/README.md](../../measurements/textured_show/README.md): 16
frames, `python scripts/run/preset.py --pipeline textured --scene S --view overview --size
1024 1024 --card 1`; the layers' parts in
[measurements/textured_frame/README.md](../../measurements/textured_frame/README.md).

## lit: direct light

Check: the shares of pixels over 2 / 4 / 8 of 255 apart and the largest error.

| scene | size | check | card frame |
| --- | --- | --- | --- |
| sponza_overview | 1024x1024 | 0.000459 / 0.000175 / 0.000106, 75 | 12.050 |
| bistro_interior_overview | 1024x1024 | 6.6e-05 / 2.7e-05 / 5e-06, 13 | 18.136 |
| bistro_exterior_overview | 1024x1024 | 0.004281 / 0.000659 / 0.000262, 109 | 27.947 |
| sponza_overview | 1280x720 | 0.000521 / 0.000185 / 0.000106, 73 | 10.882 |
| bistro_interior_overview | 1280x720 | 6.7e-05 / 2e-05 / 5e-06, 12 | 18.342 |
| bistro_exterior_overview | 1280x720 | 0.00458 / 0.000723 / 0.000254, 118 | 26.116 |
| sponza_overview | 1920x1080 | 0.000518 / 0.000186 / 9.8e-05, 85 | 18.952 |
| bistro_interior_overview | 1920x1080 | 7.6e-05 / 2.5e-05 / 5e-06, 30 | 28.914 |
| bistro_exterior_overview | 1920x1080 | 0.004608 / 0.000694 / 0.000235, 100 | 38.958 |

[measurements/lit_frame/README.md](../../measurements/lit_frame/README.md): 16 frames,
`python scripts/run/preset.py --pipeline lit --check
prism.stages.direct.light.check.thread_frame.check --scene S --view overview --size W H
--card 1`.

## gi: the field

Check: as the lit rows.

| scene | size | check | card frame |
| --- | --- | --- | --- |
| sponza_overview | 1024x1024 | 0.000772 / 0.000268 / 0.000126, 105 | 14.267 |
| bistro_interior_overview | 1024x1024 | 7.1e-05 / 2.7e-05 / 6e-06, 13 | 20.987 |
| modern_hall_overview | 1024x1024 | 8e-06 / 3e-06 / 2e-06, 11 | 13.734 |
| sponza_overview | 1280x720 | 0.000894 / 0.000299 / 0.000129, 87 | 12.800 |
| bistro_interior_overview | 1280x720 | 6.4e-05 / 2e-05 / 7e-06, 11 | 20.721 |
| modern_hall_overview | 1280x720 | 8e-06 / 2e-06 / 2e-06, 182 | 12.043 |
| sponza_overview | 1920x1080 | 0.000898 / 0.000289 / 0.00012, 106 | 23.177 |
| bistro_interior_overview | 1920x1080 | 7.3e-05 / 2.5e-05 / 5e-06, 29 | 33.894 |
| modern_hall_overview | 1920x1080 | 1.9e-05 / 1.5e-05 / 1.4e-05, 151 | 24.567 |

[measurements/gi_frame/README.md](../../measurements/gi_frame/README.md): the preset `gi`'s
static frames, 16 frames, `python scripts/run/preset.py --pipeline gi --scene S --view
overview --size W H --card 1`.

## sun: a moved sun (120, 40)

Check: the sun's map against the reference's, texels apart / one side empty; the picture
as the lit rows. The sun pass is the `sun` command that made the map before the first
frame, in ms.

| scene | size | map | picture | sun pass | card frame |
| --- | --- | --- | --- | --- | --- |
| sponza_overview | 1024x1024 | 0 / 0 | 0.000441 / 0.000141 / 3.9e-05, 77 | 19.18 | 12.080 |
| bistro_interior_overview | 1024x1024 | 0 / 0 | 6.1e-05 / 2.8e-05 / 7e-06, 13 | 32.85 | 18.108 |
| bistro_exterior_overview | 1024x1024 | 0 / 0 | 0.001556 / 0.000506 / 0.000154, 111 | 56.80 | 27.913 |

[measurements/lit_frame/README.md](../../measurements/lit_frame/README.md): the preset `lit`
with `--option "sun=(120.0, 40.0)"` added to its command.

## gi-update: the field's update on the card

Check: the picture as the lit rows; the field against the reference's for the card's
map (share of texels equal, largest code difference). The update ms is the first
update's.

| scene | size | bounces | codes | check | field | update ms | card frame |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sponza_overview | 1024x1024 | 2 | 0 | 0.000435 / 0.000153 / 5.3e-05, 93 | 0.96079, 5 | 124.87 | 14.267 |
| bistro_interior_overview | 1024x1024 | 2 | 0 | 6.5e-05 / 2.8e-05 / 6e-06, 13 | 0.58642, 6 | 134.58 | 20.954 |
| modern_hall_overview | 1024x1024 | 2 | 0 | 3.8e-05 / 4e-06 / 2e-06, 11 | 0.83576, 10 | 176.96 | 13.714 |
| sponza_overview | 1024x1024 | 0 | 0 | 0.000517 / 0.000186 / 6.9e-05, 94 | 0.99998, 1 | 100.39 | 14.256 |
| bistro_interior_overview | 1024x1024 | 0 | 0 | 6.4e-05 / 2.7e-05 / 6e-06, 12 | 0.99994, 1 | 112.06 | 20.950 |
| modern_hall_overview | 1024x1024 | 0 | 0 | 0 / 0 / 0, 1 | 0.99998, 1 | 152.26 | 13.616 |

[measurements/gi_frame/README.md](../../measurements/gi_frame/README.md) ("The update in the
loop"): the preset `gi` with `--check prism.check.field_frames.check` added to its
command, and for bounces 0 `--option bounces=0`. The update alone, in the preset
`field`, with its parts and its second update:
[measurements/field_update/README.md](../../measurements/field_update/README.md).

## apply: the transport apply alone

| set | check against the host's emulation: median / p99 / most | y sha256 | command us, median (least) |
| --- | --- | --- | --- |
| sponza | 2.12e-5 / 4.18e-4 / 4.26e-3 | cb9feed3b96afc27 | 2,609.3 (2,603.0) |
| bistro_interior | 2.68e-5 / 2.79e-4 / 1.69e-3 | 6958d5f4dbfc0443 | 4,288.0 (4,279.1) |

[measurements/apply/README.md](../../measurements/apply/README.md): the preset `apply`, 32
calls, `python scripts/run/apply.py --scene S --calls 32 --card 1`.
