# The preset `raster` with its display: visibility, then SHOW and the push

The preset `raster` is the raster stage followed by `post.show` (`configs/pipeline/raster.py`),
merged into one program. A frame's picture is the displayed one: SHOW's 8-bit pixels,
pushed to the host by the thread. The runs move the camera along a path, every frame's
picture taken and pushed.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz as the runs report it, its
  PCIe link at 16 GT/s.
- Date: 2026-11-26 (UTC+8), Komorebi at b5589ff78; every case passed, every code 0. The
  host's load average over one minute at the start of each run is in the table's last
  column (1.33 to 2.70).
- Path: `forward` of `prism.loop.path` (`--path forward`: frame i's eye moved i x 0.05
  along the view direction), 200 frames, every frame's picture taken (`--pictures`).
- Pixels: the pushed picture against the reference's vertex-colour frame converted by
  `prism_reference.post.display.to_srgb8` (R, G, B), byte for byte over the frame, in
  frames 1, 100 and 200.
- Times: the medians over all 200 frames' rows of the times region, in ms; the host's
  frame is the loop's frame and its picture, timed on the host, its median; fps is 1,000
  over it. Not tuned.

## The merged program

The raster class and the display class merged into one program, as the build of the
sponza case at 1,024 x 1,024 printed it:

| what | value |
| --- | --- |
| buffers | at shared indices of other pages (the third of the build's three ways); commands of handlers that give an index other pages do not overlap on a core |
| L1 bytes | the buffers take 915,488 B of the 1,400,576 B left for buffers |
| stack | no CPU under 256 B to spare (the load prints a line for one that is; it printed none) |

## What is here

| file | holds |
| --- | --- |
| `<scene>_overview_<W>_<H>_forward.json` | a case (named for its path): codes, the pictures of frames 1, 100, 200 (keys 0, 99, 199) against the preset's REFERENCE and JUDGE (`pictures_judged`), each time column's median and least, the host's frame, every frame's results |

Each was made by:
`python -m prism_cli run --pipeline raster --scene S --view overview --size W H --frames 200
--path forward --check 0 99 199 --pictures --card 1 --out measurements/raster_show`.

## The frames

COUNT / middle / SETUP / FILL in ms (each pass summed over the layers); SHOW, PUSH, the
card frame, the host's frame, the host's frame less the card frame, fps; the host's load
average at the start of the run.

| scene | size | pixels differ (1 / 100 / 200) | codes | COUNT / middle / SETUP / FILL | SHOW | PUSH | card frame | host frame | host - card | fps | load |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sponza_overview | 1024x1024 | 0 / 0 / 0 | [0] | 0.736 / 0.434 / 0.943 / 1.594 | 0.818 | 0.287 | 4.962 | 5.885 | 0.923 | 169.9 | 2.23 |
| bistro_interior_overview | 1024x1024 | 0 / 0 / 0 | [0] | 1.690 / 0.635 / 2.132 / 2.135 | 0.857 | 0.287 | 7.984 | 8.866 | 0.882 | 112.8 | 2.11 |
| bistro_exterior_overview | 1024x1024 | 0 / 0 / 0 | [0] | 3.395 / 0.600 / 3.903 / 4.013 | 0.888 | 0.287 | 13.340 | 14.265 | 0.925 | 70.1 | 2.07 |
| sponza_overview | 1280x720 | 0 / 0 / 0 | [0] | 0.630 / 0.512 / 0.864 / 1.351 | 0.803 | 0.259 | 4.673 | 5.455 | 0.782 | 183.3 | 2.39 |
| bistro_interior_overview | 1280x720 | 0 / 0 / 0 | [0] | 1.713 / 0.603 / 2.187 / 2.423 | 0.788 | 0.259 | 8.234 | 9.033 | 0.799 | 110.7 | 2.60 |
| bistro_exterior_overview | 1280x720 | 0 / 0 / 0 | [0] | 3.290 / 0.573 / 3.640 / 3.692 | 0.802 | 0.259 | 12.513 | 13.396 | 0.883 | 74.6 | 1.68 |
| sponza_overview | 1920x1080 | 0 / 0 / 0 | [0] | 0.815 / 0.869 / 1.387 / 2.315 | 1.583 | 0.565 | 7.813 | 9.543 | 1.730 | 104.8 | 1.92 |
| bistro_interior_overview | 1920x1080 | 0 / 0 / 0 | [0] | 1.900 / 0.875 / 2.574 / 3.821 | 1.546 | 0.565 | 11.570 | 13.042 | 1.472 | 76.7 | 2.70 |
| bistro_exterior_overview | 1920x1080 | 0 / 0 / 0 | [0] | 3.408 / 1.013 / 3.911 / 5.864 | 1.585 | 0.565 | 16.740 | 18.313 | 1.573 | 54.6 | 1.33 |

SHOW is 0.788 to 0.888 ms at 1,024 x 1,024 and 1,280 x 720 and 1.546 to 1.585 ms at
1,920 x 1,080; PUSH 0.287, 0.259 and 0.565 ms at the three sizes. The host's part of a
frame (its frame less the card frame) is 0.782 to 0.925 ms at 1,024 x 1,024 and
1,280 x 720 and 1.472 to 1.730 ms at 1,920 x 1,080. Host times on this machine move with
the load of the other work on it.
