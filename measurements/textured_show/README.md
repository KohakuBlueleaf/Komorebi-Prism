# The preset `textured` with its display: SHADE's colour shown and pushed

The preset `textured` is the raster stage, the texture stage (SHADE) and `post.show`
(`configs/pipeline/textured.py`), merged into one program; the picture is the card's
display of the frame SHADE left. The same preset without its display, the picture made on
the host, is in `measurements/textured_frame/`.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz as the runs report it, its
  PCIe link at 16 GT/s.
- Date: 2026-11-26 (UTC+8), Komorebi at b5589ff78; every case
  passed at the first attempt, every code 0.
- Each case: `scripts/run/preset.py --pipeline textured --scene S --view overview --size
  1024 1024 --card 1 --out measurements/textured_show`, 16 frames; the times are the
  medians of the last rows, in ms, by layer (`part` the first layer's, `part.<i>` layer
  i's).
- Pass: the pictures of frames 1, 2 and 16 against `prism_reference`'s shaded frame
  (`stages/material/texture/model/expect.check`): pixels that differ and the largest error
  no more than `measurements/textured_frame/`'s; the pushed picture and the display read
  back against the frame's colour converted on the host (`to_srgb8`), bit for bit; frames
  1 and 16 the same picture.

## What is here

| file | holds |
| --- | --- |
| `<scene>_overview_1024_1024.json` | the harness record: frames, codes, the pipeline, each checked picture's report, whether the pictures match, the parts' medians by layer |

## Pictures and times

Pixels that differ / the largest error against the reference (textured_frame's: sponza
8 / 16, bistro_interior 62 / 21, bistro_exterior 3 / 11); pixels that differ from the
host's conversion of the frame, pushed / read back; SHOW, PUSH and the card frame, in ms.

| scene | pixels differ / largest error | host's conversion (pushed / read back) | frame 1 = frame 16 | SHOW | PUSH | card frame |
| --- | --- | --- | --- | --- | --- | --- |
| sponza | 8 / 16 | 0 / 0 | yes | 0.813 | 0.288 | 10.781 |
| bistro_interior | 62 / 21 | 0 / 0 | yes | 0.865 | 0.287 | 15.442 |
| bistro_exterior | 3 / 11 | 0 / 0 | yes | 0.819 | 0.287 | 27.688 |

The layers' parts are those of `measurements/textured_frame/` within 0.015 ms.
