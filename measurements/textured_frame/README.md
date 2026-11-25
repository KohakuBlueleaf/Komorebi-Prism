# The preset `textured`: a shaded frame as one command to the X280 thread

The raster stage's passes for every layer, then SHADE for every layer, run by the
director's FRAME command (one thread command a frame); the preset without its display.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz as the runs report it; its
  PCIe link at 16 GT/s.
- Date: 2026-11-25 (UTC+8); every record from one build of the tree.
- Each case: `scripts/run/preset.py --pipeline textured --no-display --scene S --view
  overview --size 1024 1024 --card 1 --out measurements/textured_frame`, 16 frames; the
  times are the medians of the times rows, in ms, by layer.
- Pass: the pictures of frames 1 and 16 against `prism_reference`'s shaded frame
  (`stages/material/texture/model/expect.check`); frames 1 and 16 the same picture; every
  code 0.

## What is here

| file | holds |
| --- | --- |
| `<scene>_overview_<W>_<H>.json` | the harness record: frames, codes, layers, each checked picture's report, whether frames 1 and 16 match, the parts' medians by layer (`part` the first layer's, `part.<i>` layer i's) |

## Pictures

| scene | layers | pixels differ / largest error | frame 1 = frame 16 |
| --- | --- | --- | --- |
| breakfast_room | opaque | 6 / 8 | yes |
| sponza | opaque, masked | 8 / 16 | yes |
| bistro_interior | opaque, masked, glass | 62 / 21 | yes |
| bistro_exterior | opaque, masked, glass | 3 / 11 | yes |

## Times, layer by layer

In ms; "raster" is the layer's eight passes summed (COUNT, SUM, HIST, HSUM, middle, PLACE,
SETUP, FILL). Reported, not tuned.

| scene | layer | COUNT | middle | SETUP | FILL | raster | SHADE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sponza | opaque | 0.671 | 0.447 | 0.861 | 1.485 | 3.609 | 4.132 |
| sponza | masked | 0.109 | 0.712 | 0.223 | 0.161 | 1.451 | 0.494 |
| bistro_interior | opaque | 1.259 | 0.638 | 1.680 | 1.768 | 5.594 | 4.565 |
| bistro_interior | masked | 0.091 | 0.564 | 0.163 | 0.143 | 1.202 | 0.187 |
| bistro_interior | glass | 0.388 | 0.680 | 0.507 | 0.435 | 2.254 | 0.477 |
| bistro_exterior | opaque | 2.500 | 0.434 | 2.867 | 2.629 | 8.576 | 6.625 |
| bistro_exterior | masked | 0.851 | 0.709 | 1.914 | 1.898 | 5.619 | 4.230 |
| bistro_exterior | glass | 0.089 | 0.576 | 0.153 | 0.130 | 1.190 | 0.313 |

The frame; the parts are every layer's passes and SHADEs summed, and the frame less them
is the thread's time between commands.

| scene | frame | parts | between commands |
| --- | --- | --- | --- |
| sponza | 9.686 | 9.686 | 0.000 |
| bistro_interior | 14.280 | 14.278 | 0.002 |
| bistro_exterior | 26.566 | 26.553 | 0.013 |

The time between commands is under 0.02 ms. A small layer (sponza's and
bistro_interior's masked, bistro_exterior's glass) costs 1.19 to 1.45 ms of raster, about
half of it the middle pass (0.56 to 0.71 ms).
