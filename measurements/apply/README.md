# The transport's apply alone: the preset `apply`

One apply `y = M x` of a scene's light-transport matrix (`indirect.transport`, the preset
`apply`), 32 calls in one load.

- Card: one Blackhole P150A, card 1, 120 cores, AICLK 1,350 MHz as the runs report it.
- Date: 2026-11-26 (UTC+8), Komorebi at b5589ff78.
- Each case: `python scripts/run/apply.py --scene S --calls 32 --card 1`, its record
  `apply_<scene>.json`.

The errors are of each element's luminance over the lit elements: against the host's
emulation of the card's numbers, and against the set's float32 result `y_float.npy`. A
command's time is its event's, over the 32 calls.

| scene | against the emulation: median / p99 / most | against y_float: median / p99 / sum ratio | command us: median / least | y's hash |
| --- | --- | --- | --- | --- |
| sponza | 2.12e-5 / 4.18e-4 / 4.26e-3 | 1.15e-3 / 2.15e-2 / 0.99985 | 2,609.3 / 2,603.0 | cb9feed3b96afc27 |
| bistro_interior | 2.68e-5 / 2.79e-4 / 1.69e-3 | 6.04e-4 / 8.05e-3 / 0.99976 | 4,288.0 / 4,279.1 | 6958d5f4dbfc0443 |

The last of the 32 calls gives the same y as the first, word for word.
