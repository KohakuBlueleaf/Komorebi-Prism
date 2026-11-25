# The lit frame with the indirect field

The static field first: the preset `lit`'s classes (raster, material.texture,
direct.shadow_pcf, direct.light, post.show) with the term `indirect` on: LIGHT adds the
field read from the light pages (slot `light.field`), the field the set's own, made once
at load. Then the preset `gi` (`configs/pipeline/gi.py`): the same with the transport's
`Apply` merged in its frame form (its streams and sums inside the common field
`command_space`, `stages/indirect/transport/README.md`) and the field's update in the
loop.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz as the runs report it, its
  link to the host at 16 GT/s.
- Date: 2026-11-26 (UTC+8), Komorebi at b5589ff78, every record but `apply_sponza_frame_form.json` (2026-11-25,
  an earlier build).
- Each case: 1,024 x 1,024 (the preset `gi`'s static frames also at 1,280 x 720 and
  1,920 x 1,080, below), 16 frames, the overview view, the scene's materials, name
  and lights given; the times the medians of the times rows in ms.
- Pass: frames 1, 2 and 16 against `prism_reference`'s lit frame with the field
  (`stages/direct/light/check/thread_frame.reference_picture`): the shares of pixels over
  2 / 4 / 8 of 255 apart and the largest error, as recorded; frames 1 and 16 the same
  picture; every code 0. The switch `direct.light.indirect` off: the reference without
  the term indirect, which is the preset `lit`'s.

## What is here

Each record is `scripts/run/preset.py ... --scene S --view overview --size W H --card 1`
with:

| file | holds | the runner's arguments |
| --- | --- | --- |
| `<scene>_overview_1024_1024_static.json` | the four classes with the static field: codes, each checked picture's report, whether frames 1 and 16 match, the parts' medians by layer (`part` the first layer's, `part.<i>` layer i's) | `--pipeline lit --option "terms=('sky', 'ambient', 'sun', 'shadow', 'lamps', 'specular', 'background', 'glass', 'indirect')"` |
| `<scene>_overview_1024_1024_indirect_off.json` | the preset `gi` with the switch off, as the static records | `--pipeline gi --set direct.light.indirect=False` |
| `<scene>_overview_1024_1024_gi.json` | the preset `gi`'s static frames (five classes in one program), as the static records | `--pipeline gi` |
| `<scene>_overview_<W>_<H>_gi.json` | the same at 1,280 x 720 and 1,920 x 1,080 | `--pipeline gi` |
| `<scene>_overview_1024_1024_update_b<n>.json` | the preset `gi` with `prism.check.field_frames.check`, bounces 2 and 0: each sun in turn (its frames, the field against the reference's for the card's map, the pictures), the scale words, the update's times | `--pipeline gi --check prism.check.field_frames.check`, and for bounces 0 `--option bounces=0` |
| `apply_sponza_frame_form.json` | `Apply` alone in its frame form, its y's hash and times | `scripts/run/apply.py --frame-compute` (not the preset runner) |

## Pictures

Frame 1 (frames 2 and 16 the same in every case). The four classes with the static field
and the five of the preset `gi` give the same numbers.

| scene | shares over 2 / 4 / 8, largest error | switch off |
| --- | --- | --- |
| sponza | 0.000772 / 0.000268 / 0.000126, 105 | 0.000459 / 0.000175 / 0.000106, 75 |
| bistro_interior | 7.1e-05 / 2.7e-05 / 6e-06, 13 | 6.6e-05 / 2.7e-05 / 5e-06, 13 |
| modern_hall | 8e-06 / 3e-06 / 2e-06, 11 | 7e-06 / 4e-06 / 3e-06, 11 |

With the switch off, sponza's and bistro_interior's numbers are those of the preset
`lit` (`measurements/lit_frame/`).

## Times on the card

The preset `gi` (`*_gi.json`). The frame is the director's whole FRAME with the push;
raster the eight passes (COUNT, SUM, HIST, HSUM, middle, PLACE, SETUP, FILL) over every
layer; SHADE every layer; LIGHT with its glass form, the glass form's part apart.

| scene | frame | raster | SHADE | LIGHT | LIGHT glass | SHOW | push |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sponza | 14.267 | 5.040 | 4.156 | 3.992 | - | 0.793 | 0.286 |
| bistro_interior | 20.987 | 9.059 | 4.659 | 6.123 | 1.257 | 0.864 | 0.286 |
| modern_hall | 13.734 | 2.324 | 2.207 | 8.082 | 2.147 | 0.831 | 0.286 |

The four classes with the static field: frame sponza 14.288, bistro_interior 20.998, modern_hall 13.744 ms. The field
adds to LIGHT alone: sponza's LIGHT is 1.748 ms in `lit` (`measurements/lit_frame/`),
3.992 ms here.

## Five classes in one program

The preset `gi`'s pictures are the static records' to the pixel on the three scenes.
The command space (`prism.core.fields`) is 639,104 B at each capacity: the texel layout
(slots 528,384, the pack CPU's work 102,512, the page passes' hash 8,192) over the
raster's (counters and histograms: 73,728 B, 147,456 at 1,920 x 1,080) and SHOW's
(16,384). As the builds of these records printed them: the buffers at shared indices of
other pages (way 3 of 3), 1,087,776 B at 1,024 x 1,024 and 1,280 x 720 and 1,120,544 B
at 1,920 x 1,080, of 1,209,504 to 1,210,752 B left for them (the room follows the kernel
buffer of the load); the pack CPU's (TRISC2) stack 1,648 / 1,504 / 144 B (room / need /
margin) on sponza, 1,632 / 1,504 / 128 B on the other two. Komorebi warns of that margin
(under 256 B) on each.

`Apply` in the frame form by itself gives y's hash of the resident form,
`cb9feed3b96afc27`; its card time a call, median: 2,613.36 us (resident, HiFi2:
2,609.25).

## The update in the loop

The sun (120, 40), then (200, 30): the loop sends `sun`, `update`, `field_scale`, then
frames. Pictures of frame 1 at (120, 40) (frame 16 the same); the field against the
reference's for the card's map, and the record's verdict (the rule of
`measurements/field_update/`); the update's card time (its first, in ms).

| scene | bounces | shares over 2 / 4 / 8, largest error | field: share equal, code most | update |
| --- | --- | --- | --- | --- |
| sponza | 2 | 0.000435 / 0.000153 / 5.3e-05, 93 | 0.96079, 5, passed | 124.87 |
| sponza | 0 | 0.000517 / 0.000186 / 6.9e-05, 94 | 0.99998, 1, passed | 100.39 |
| bistro_interior | 2 | 6.5e-05 / 2.8e-05 / 6e-06, 13 | 0.58642, 6, passed | 134.58 |
| bistro_interior | 0 | 6.4e-05 / 2.7e-05 / 6e-06, 12 | 0.99994, 1, passed | 112.06 |
| modern_hall | 2 | 3.8e-05 / 4e-06 / 2e-06, 11 | 0.83576, 10, passed | 176.96 |
| modern_hall | 0 | 0 / 0 / 0, 1 | 0.99998, 1, passed | 152.26 |

At the second sun (200, 30), bounces 2: share equal, code most and scale relative sponza
0.95734, 9, 2.36e-06; bistro_interior 0.58024, 6, 0.00294; modern_hall 0.83810, 10,
0.00139 (the records' verdicts hold these to the (120, 40) rows and say failed for sponza
and bistro_interior); bounces 0 gives code most 1 on each. Every code 0; the scale words
and the units LIGHT computes equal the times rows' bits.

## Running

```bash
python scripts/run/preset.py --pipeline PRESET --scene S --view overview --size 1024 1024 --card 1
```

`--pipeline` takes a preset's name in `configs/pipeline/`; the other arguments of each
record are in "What is here".

## The static frames at 1,280 x 720 and 1,920 x 1,080

The preset `gi`'s static frames, each case `scripts/run/preset.py --pipeline gi --scene S
--view overview --size W H --card 1`, 16 frames, the build of the records at
1,024 x 1,024, card 1 (link 16 GT/s), AICLK 1,350 MHz before and after, 2026-11-26
(UTC+8); every code 0, frames 1, 2 and 16 the same picture. These runs record the card's
times only, not the host's frame.

Frame 1's shares over 2 / 4 / 8 of 255 and the largest error:

| scene | size | shares over 2 / 4 / 8, largest error |
| --- | --- | --- |
| sponza | 1280x720 | 0.000894 / 0.000299 / 0.000129, 87 |
| bistro_interior | 1280x720 | 6.4e-05 / 2e-05 / 7e-06, 11 |
| modern_hall | 1280x720 | 8e-06 / 2e-06 / 2e-06, 182 |
| sponza | 1920x1080 | 0.000898 / 0.000289 / 0.00012, 106 |
| bistro_interior | 1920x1080 | 7.3e-05 / 2.5e-05 / 5e-06, 29 |
| modern_hall | 1920x1080 | 1.9e-05 / 1.5e-05 / 1.4e-05, 151 |

The frame and its parts, as the table at 1,024 x 1,024 above:

| scene | size | frame | raster | SHADE | LIGHT | LIGHT glass | SHOW | push |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sponza | 1280x720 | 12.800 | 4.765 | 3.611 | 3.454 | - | 0.706 | 0.258 |
| bistro_interior | 1280x720 | 20.721 | 9.543 | 4.745 | 5.387 | 1.096 | 0.786 | 0.258 |
| modern_hall | 1280x720 | 12.043 | 1.848 | 1.860 | 7.336 | 2.194 | 0.734 | 0.258 |
| sponza | 1920x1080 | 23.177 | 7.683 | 6.062 | 7.332 | - | 1.528 | 0.564 |
| bistro_interior | 1920x1080 | 33.894 | 13.397 | 7.631 | 10.755 | 2.107 | 1.541 | 0.564 |
| modern_hall | 1920x1080 | 24.567 | 3.716 | 3.803 | 14.915 | 4.094 | 1.566 | 0.564 |
