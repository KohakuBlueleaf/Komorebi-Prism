# The pages a frame's lookups read

A model, on the host, of the pages SHADE and LIGHT ask mover A for in a frame. It covers
the three tables read this way: the scene's textures (SHADE), the sun's shadow map with
the background's octahedral map (LIGHT's taps) and the indirect field (LIGHT, with the
term `indirect`). It also counts how many pages an item reads, how regular they are, and
how many pages a core would read if its slots kept pages across passes, items and frames.
No card was run: every number here comes from `prism_reference` and the raster model.

- Date: 2026-11-26 (UTC+8), host only (numpy).
- Each case: `scripts/run/lookup_model.py --scene S --view V --size W H [--terms
  indirect] [--frames 16]`; the record is `<scene>_<view>_<W>_<H>.json` beside this page.
  `gi` cases add `--terms indirect` (the field); `lit` cases use the default terms. The
  across-frames numbers are from `--frames 16` (sponza and bistro_interior at 1,920 x
  1,080). The forward path is `prism.loop.path.forward`: the eye moves 0.05 a frame
  along the view direction.
- Tables: `prism_reference.material.access` (texture pages),
  `prism_reference.direct.access` (light pages), `prism.check.lookup` (items, deal,
  passes, kept slots).

## The model

- **Pixels and pages.** Per pixel of the padded frame: each layer's texture keys as lit
  SHADE makes them (albedo, normal, specular, the masked layer's mask), the four shadow
  taps of a covered pixel (an empty pixel: the background's three channels) and the
  eight field corners. Each key is numbered as the card numbers its pages. The first
  pages of LIGHT's maps come from LIGHT's own table (`light_table`).
- **Items and their deal.** Each layer's COUNT numbers come from the reference's setup:
  per tile its entries, rows and 2-row groups. From these, the raster model cuts heavy
  tiles into bands and deals the items to 120 cores, largest estimated cost first.
  SHADE walks each layer's items (an item without entries makes no pass); LIGHT walks
  the opaque layer's items. A core's items run in tile order, and SHADE's layers run
  one after another.
- **Passes (today).** A pass is an item in SHADE, or a quarter of 8 rows in LIGHT (its
  shadow taps and its field are separate passes). Rows join a pass while their distinct
  pages fit 128 slots; the row that would need slot 129 starts the next pass. The pages
  asked are the pass's distinct pages; a pass with no pages asks nothing but still
  counts as a pass.
- **Kept within a frame.** The same passes, but each core's 128 slots keep their pages
  (least recently used out) instead of being emptied at each pass. `reads` are the pass
  pages not already in the slots.
- **Kept across frames.** The slots also persist from frame to frame along the forward
  path, with the deal recomputed each frame from that frame's counts. With 64, 256 or
  512 slots, a pass is also bounded by that many slots. "reads a frame" is the mean over
  frames 2 to 16. "hit rate" is 1 - reads / pages asked by those frames' passes at that
  slot count.
- **Per table.** Each table is modelled with its own slots. On the card, LIGHT's taps and
  field share one hash but use it in separate passes.

Not modelled: LIGHT's glass form (`light_glass`, the bistro_exterior record's 6,291 pages
on its glass quarters).

## The check against the card

The model's first frame against `measurements/account/<scene>_<view>_<W>_<H>_<pipeline>.json`
(`stages[].items` summed over the cores: the profiles' pages, passes and texels of SHADE,
over its layers, and of LIGHT). Each cell gives model / card (ratio). italian_flat has no
account record.

| case | record | SHADE pages model / card (ratio) | SHADE passes | SHADE texels | LIGHT pages | LIGHT passes | field pages | field passes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sponza overview 1024 x 1024 (gi) | `sponza_overview_1024_1024_gi` | 43,653 / 44,105 (0.9898) | 1,487 / 1,487 (1.0000) | 1,820,047 / 1,820,047 (1.0000) | 12,620 / 12,622 (0.9998) | 4,096 / 4,096 (1.0000) | 11,088 / 11,089 (0.9999) | 4,096 / 4,096 (1.0000) |
| sponza overview 1920 x 1080 (gi) | `sponza_overview_1920_1080_gi` | 50,941 / 51,040 (0.9981) | 2,427 / 2,427 (1.0000) | 3,790,771 / 3,790,771 (1.0000) | 18,026 / 18,029 (0.9998) | 8,160 / 8,160 (1.0000) | 19,304 / 19,305 (0.9999) | 8,160 / 8,160 (1.0000) |
| bistro_interior overview 1024 x 1024 (gi) | `bistro_interior_overview_1024_1024_gi` | 19,732 / 19,732 (1.0000) | 1,639 / 1,639 (1.0000) | 1,877,058 / 1,877,058 (1.0000) | 12,577 / 12,580 (0.9998) | 4,202 / 4,202 (1.0000) | 13,606 / 13,606 (1.0000) | 4,202 / 4,202 (1.0000) |
| bistro_interior overview 1920 x 1080 (gi) | `bistro_interior_overview_1920_1080_gi` | 34,506 / 34,506 (1.0000) | 2,668 / 2,668 (1.0000) | 3,820,173 / 3,820,173 (1.0000) | 21,066 / 21,067 (1.0000) | 8,160 / 8,160 (1.0000) | 23,690 / 23,689 (1.0000) | 8,160 / 8,160 (1.0000) |
| modern_hall overview 1024 x 1024 (gi) | `modern_hall_overview_1024_1024_gi` | 4,622 / 4,622 (1.0000) | 1,204 / 1,204 (1.0000) | 434,946 / 434,946 (1.0000) | 11,716 / 11,720 (0.9997) | 4,122 / 4,122 (1.0000) | 16,198 / 16,192 (1.0004) | 4,122 / 4,122 (1.0000) |
| modern_hall overview 1920 x 1080 (gi) | `modern_hall_overview_1920_1080_gi` | 6,611 / 6,611 (1.0000) | 2,260 / 2,260 (1.0000) | 748,169 / 748,169 (1.0000) | 18,701 / 18,705 (0.9998) | 8,160 / 8,160 (1.0000) | 25,170 / 25,167 (1.0001) | 8,160 / 8,160 (1.0000) |
| bistro_exterior overview 1024 x 1024 (lit) | `bistro_exterior_overview_1024_1024_lit` | 39,908 / 39,909 (1.0000) | 2,110 / 2,110 (1.0000) | 2,515,524 / 2,515,524 (1.0000) | 10,911 / 10,907 (1.0004) | 4,096 / 4,096 (1.0000) | - | - |
| bistro_exterior overview 1920 x 1080 (lit) | `bistro_exterior_overview_1920_1080_lit` | 73,870 / 73,871 (1.0000) | 3,530 / 3,530 (1.0000) | 5,196,683 / 5,196,683 (1.0000) | 16,830 / 16,830 (1.0000) | 8,160 / 8,160 (1.0000) | - | - |
| italian_flat camera 1024 x 1024 (lit) | none | | | | | | | |
| italian_flat camera 1920 x 1080 (lit) | none | | | | | | | |

## The tables

One row per case, all numbers from the model's first frame unless marked. The columns:

- `pages`, `passes`: today's pages asked in a frame and the passes, summed over cores.
- `items`: items that make passes. `item pages`: the distinct pages of an item (the
  union over its passes): median / 99th percentile / most.
- `box`: the bounding box of an item's pages in the table's own page grid, in pages.
  For textures, one box per texture and level, summed. For the shadow map, one for the
  map and one for each background channel, summed. For the field, the box of its
  blocks in x, y and z. Median / 99th percentile, over items with pages.
- `box read`: the share of the box the item really reads, pooled (all items' distinct
  pages over all their boxes) / the median item's.
- `items box <= 2 / 4 / 8 / 16 / 32`: the share of items (with pages) whose box is at
  most that many pages.
- `kept in frame`: reads a frame with 128 kept slots (and their share of today's pages).
- `across`: for 64 / 128 / 256 / 512 kept slots, reads a frame after the first, then
  the hit rate.
- `lookups a pixel`: texels the card gathers per pixel (textures: 3 per keyed pixel of
  a layer, white where none; taps: 4; field: 8 corners x 3 axes), then keys that name a
  page per pixel (textures: over the layers' keyed pixels, mask included; taps and
  field: over covered pixels).

### Textures (SHADE, all layers)

| case | pages | passes | items | item pages median / 99th / most | box median / 99th | box read pooled / item median | items box <= 2 / 4 / 8 / 16 / 32 | kept in frame (share) | across: 64 / 128 / 256 / 512 reads a frame (hit rate) | lookups a pixel: gathered / keys |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| sponza overview 1024 x 1024 (gi) | 43,653 | 1,487 | 1,388 | 14 / 247 / 470 | 16 / 1068 | 0.385 / 0.875 | 0.03 / 0.08 / 0.24 / 0.50 / 0.69 | 41,379 (0.948) | - | 3 / 1.75 |
| sponza overview 1920 x 1080 (gi) | 50,941 | 2,427 | 2,408 | 12 / 123 / 176 | 18 / 877 | 0.337 / 0.857 | 0.01 / 0.05 / 0.21 / 0.48 / 0.68 | 49,136 (0.965) | 49,532 (0.059) / 49,136 (0.037) / 48,066 (0.057) / 39,238 (0.230) | 3 / 1.80 |
| bistro_interior overview 1024 x 1024 (gi) | 19,732 | 1,639 | 1,639 | 10 / 55 / 87 | 16 / 189 | 0.574 / 0.861 | 0.06 / 0.11 / 0.25 / 0.53 / 0.77 | 18,766 (0.951) | - | 3 / 1.80 |
| bistro_interior overview 1920 x 1080 (gi) | 34,506 | 2,668 | 2,668 | 8 / 58 / 111 | 12 / 253 | 0.472 / 0.900 | 0.05 / 0.16 / 0.42 / 0.56 / 0.69 | 31,395 (0.910) | 32,169 (0.080) / 31,569 (0.092) / 27,063 (0.222) / 19,999 (0.425) | 3 / 1.84 |
| modern_hall overview 1024 x 1024 (gi) | 4,622 | 1,204 | 1,204 | 0 / 20 / 27 | 13 / 139 | 0.372 / 0.708 | 0.06 / 0.11 / 0.29 / 0.61 / 0.82 | 4,523 (0.979) | - | 3 / 0.39 |
| modern_hall overview 1920 x 1080 (gi) | 6,611 | 2,260 | 2,260 | 0 / 15 / 22 | 14 / 251 | 0.188 / 0.571 | 0.06 / 0.15 / 0.36 / 0.56 / 0.68 | 6,389 (0.966) | - | 3 / 0.34 |
| bistro_exterior overview 1024 x 1024 (lit) | 39,908 | 2,110 | 2,109 | 8 / 87 / 165 | 20 / 475 | 0.468 / 0.922 | 0.07 / 0.20 / 0.38 / 0.47 / 0.60 | 33,929 (0.850) | - | 3 / 2.06 |
| bistro_exterior overview 1920 x 1080 (lit) | 73,870 | 3,530 | 3,528 | 12 / 87 / 144 | 30 / 831 | 0.368 / 0.786 | 0.04 / 0.10 / 0.24 / 0.38 / 0.53 | 64,844 (0.878) | - | 3 / 2.05 |
| italian_flat camera 1024 x 1024 (lit) | 5,930 | 1,148 | 1,148 | 0 / 34 / 44 | 16 / 355 | 0.458 / 1.000 | 0.00 / 0.11 / 0.30 / 0.56 / 0.91 | 5,129 (0.865) | - | 3 / 0.58 |
| italian_flat camera 1920 x 1080 (lit) | 11,539 | 2,403 | 2,403 | 0 / 36 / 70 | 16 / 456 | 0.406 / 1.000 | 0.03 / 0.10 / 0.34 / 0.57 / 0.82 | 9,468 (0.821) | - | 3 / 0.48 |

### Shadow map with the background (LIGHT)

| case | pages | passes | items | item pages median / 99th / most | box median / 99th | box read pooled / item median | items box <= 2 / 4 / 8 / 16 / 32 | kept in frame (share) | across: 64 / 128 / 256 / 512 reads a frame (hit rate) | lookups a pixel: gathered / keys |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| sponza overview 1024 x 1024 (gi) | 12,620 | 4,096 | 1,024 | 3 / 14 / 17 | 4 / 165 | 0.254 / 0.750 | 0.35 / 0.55 / 0.64 / 0.75 / 0.87 | 3,916 (0.310) | - | 4 / 4.00 |
| sponza overview 1920 x 1080 (gi) | 18,026 | 8,160 | 2,040 | 2 / 8 / 13 | 2 / 146 | 0.258 / 1.000 | 0.53 / 0.70 / 0.76 / 0.83 / 0.91 | 4,830 (0.268) | 2,598 (0.856) / 1,510 (0.916) / 1,191 (0.934) / 1,191 (0.934) | 4 / 4.00 |
| bistro_interior overview 1024 x 1024 (gi) | 12,577 | 4,202 | 1,156 | 3 / 19 / 23 | 4 / 173 | 0.286 / 1.000 | 0.45 / 0.63 / 0.71 / 0.79 / 0.86 | 5,061 (0.402) | - | 4 / 4.00 |
| bistro_interior overview 1920 x 1080 (gi) | 21,066 | 8,160 | 2,040 | 3 / 14 / 19 | 4 / 161 | 0.253 / 1.000 | 0.48 / 0.62 / 0.72 / 0.81 / 0.87 | 6,951 (0.330) | 5,709 (0.729) / 4,245 (0.798) / 2,915 (0.862) / 2,528 (0.880) | 4 / 4.00 |
| modern_hall overview 1024 x 1024 (gi) | 11,716 | 4,122 | 1,054 | 4 / 26 / 32 | 4 / 118 | 0.429 / 1.000 | 0.36 / 0.63 / 0.78 / 0.87 / 0.92 | 4,800 (0.410) | - | 4 / 4.00 |
| modern_hall overview 1920 x 1080 (gi) | 18,701 | 8,160 | 2,040 | 3 / 14 / 20 | 4 / 86 | 0.407 / 1.000 | 0.45 / 0.69 / 0.81 / 0.89 / 0.93 | 6,655 (0.356) | - | 4 / 4.00 |
| bistro_exterior overview 1024 x 1024 (lit) | 10,911 | 4,096 | 1,024 | 2 / 13 / 22 | 2 / 125 | 0.438 / 1.000 | 0.50 / 0.73 / 0.82 / 0.92 / 0.96 | 3,253 (0.298) | - | 4 / 4.00 |
| bistro_exterior overview 1920 x 1080 (lit) | 16,830 | 8,160 | 2,040 | 2 / 8 / 13 | 2 / 56 | 0.458 / 1.000 | 0.60 / 0.80 / 0.88 / 0.95 / 0.97 | 4,152 (0.247) | - | 4 / 4.00 |
| italian_flat camera 1024 x 1024 (lit) | 12,659 | 4,208 | 1,184 | 3 / 14 / 20 | 4 / 59 | 0.526 / 1.000 | 0.32 / 0.56 / 0.77 / 0.87 / 0.96 | 4,552 (0.360) | - | 4 / 4.00 |
| italian_flat camera 1920 x 1080 (lit) | 17,529 | 8,160 | 2,040 | 2 / 13 / 21 | 2 / 54 | 0.545 / 1.000 | 0.64 / 0.80 / 0.86 / 0.92 / 0.98 | 4,774 (0.272) | - | 4 / 4.00 |

### Field (LIGHT, term indirect)

| case | pages | passes | items | item pages median / 99th / most | box median / 99th | box read pooled / item median | items box <= 2 / 4 / 8 / 16 / 32 | kept in frame (share) | across: 64 / 128 / 256 / 512 reads a frame (hit rate) | lookups a pixel: gathered / keys |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| sponza overview 1024 x 1024 (gi) | 11,088 | 4,096 | 1,024 | 3 / 9 / 10 | 3 / 30 | 0.572 / 1.000 | 0.48 / 0.71 / 0.83 / 0.90 / 1.00 | 3,030 (0.273) | - | 24 / 8.00 |
| sponza overview 1920 x 1080 (gi) | 19,304 | 8,160 | 2,040 | 2 / 7 / 9 | 2 / 30 | 0.631 / 1.000 | 0.63 / 0.83 / 0.89 / 0.93 / 1.00 | 4,156 (0.215) | 1,334 (0.931) / 667 (0.966) / 666 (0.966) / 666 (0.966) | 24 / 8.00 |
| bistro_interior overview 1024 x 1024 (gi) | 13,606 | 4,202 | 1,156 | 3 / 17 / 23 | 3 / 153 | 0.365 / 1.000 | 0.48 / 0.65 / 0.76 / 0.84 / 0.91 | 5,024 (0.369) | - | 24 / 8.00 |
| bistro_interior overview 1920 x 1080 (gi) | 23,690 | 8,160 | 2,040 | 3 / 14 / 19 | 3 / 140 | 0.352 / 1.000 | 0.47 / 0.65 / 0.77 / 0.84 / 0.92 | 7,264 (0.307) | 5,694 (0.760) / 3,755 (0.842) / 2,338 (0.901) / 2,112 (0.911) | 24 / 8.00 |
| modern_hall overview 1024 x 1024 (gi) | 16,198 | 4,122 | 1,054 | 4 / 27 / 38 | 4 / 491 | 0.250 / 1.000 | 0.20 / 0.51 / 0.72 / 0.83 / 0.88 | 6,429 (0.397) | - | 24 / 8.00 |
| modern_hall overview 1920 x 1080 (gi) | 25,170 | 8,160 | 2,040 | 4 / 18 / 26 | 4 / 252 | 0.284 / 1.000 | 0.32 / 0.62 / 0.78 / 0.85 / 0.90 | 8,887 (0.353) | - | 24 / 8.00 |
| bistro_exterior overview 1024 x 1024 (lit) | no field | | | | | | | | | |
| bistro_exterior overview 1920 x 1080 (lit) | no field | | | | | | | | | |
| italian_flat camera 1024 x 1024 (lit) | no field | | | | | | | | | |
| italian_flat camera 1920 x 1080 (lit) | no field | | | | | | | | | |

## An item's extent in the table's own unit

The same items, deal and first frame, measured in each table's finest unit rather than
in pages. Each statistic is over the items that read at least one texel of that table.

- **Shadow map.** The bounding rectangle of an item's taps, in texels of the map:
  width and height (median / 99th percentile / most), the share of items whose
  rectangle fits 32 x 32, 64 x 64, 128 x 128 and 256 x 256 texels, and the share of the
  rectangle's texels the item reads (distinct tap texels over the rectangle). The
  background's texels are not included.
- **Field.** The bounding box of the corner voxels an item reads (cells along x, y, z:
  medians, then 99th percentiles), its distinct voxels (median / 99th / most), the share
  of items with at most 64, 128, 256, 512 and 1,024 distinct voxels, and the share of
  the box read (distinct voxels over the box's).
- **Textures.** The distinct (texture, mip level) pairs an item reads (median / 99th /
  most) and, per pair, the bounding rectangle of its texels in that level. "within"
  gives the share of pairs whose rectangle fits 32 x 32, 64 x 64 and 128 x 128 texels,
  first pooled over every item's pairs, then as the mean over items of an item's share.
- **A row of 32 pixels.** For the shadow map, a row's tap rectangle (width and height,
  median / 99th percentile, over rows with taps). For the field, the lookup's cells (the
  floor of the pixel's grid point, before the eight corners; a pixel with no corner on
  the grid is left out): the distinct cells an item's pixels fall in (median / 99th /
  most) and a row's (median / 99th), with the share of rows having 1, at most 2 and at
  most 4 distinct cells.
### Shadow map, in texels

| case | width median / 99th / most | height median / 99th / most | items within 32 / 64 / 128 / 256 squared | share read median / mean | a row of 32: width median / 99th, height median / 99th |
| --- | --- | --- | --- | --- | --- |
| sponza overview 1024 x 1024 (gi) | 30 / 440 / 576 | 35 / 446 / 651 | 0.46 / 0.64 / 0.75 / 0.87 | 0.272 / 0.286 | 19 / 351, 20 / 371 |
| sponza overview 1920 x 1080 (gi) | 18 / 394 / 467 | 21 / 411 / 648 | 0.64 / 0.76 / 0.85 / 0.91 | 0.413 / 0.366 | 12 / 333, 12 / 394 |
| bistro_interior overview 1024 x 1024 (gi) | 23 / 353 / 514 | 24 / 572 / 643 | 0.53 / 0.71 / 0.81 / 0.91 | 0.527 / 0.490 | 13 / 269, 8 / 557 |
| bistro_interior overview 1920 x 1080 (gi) | 19 / 339 / 474 | 22 / 564 / 644 | 0.56 / 0.73 / 0.81 / 0.92 | 0.498 / 0.485 | 10 / 253, 7 / 554 |
| modern_hall overview 1024 x 1024 (gi) | 31.5 / 383 / 558 | 28 / 352 / 583 | 0.45 / 0.72 / 0.85 / 0.93 | 0.623 / 0.565 | 20 / 383, 5 / 244 |
| modern_hall overview 1920 x 1080 (gi) | 23 / 328 / 509 | 24 / 310 / 571 | 0.53 / 0.76 / 0.87 / 0.95 | 0.610 / 0.535 | 15 / 328, 6 / 208 |
| bistro_exterior overview 1024 x 1024 (lit) | 17 / 280 / 393 | 23 / 371 / 492 | 0.60 / 0.81 / 0.93 / 0.98 | 0.392 / 0.382 | 11 / 187, 13 / 219 |
| bistro_exterior overview 1920 x 1080 (lit) | 13 / 213 / 378 | 16 / 242 / 435 | 0.68 / 0.85 / 0.95 / 0.99 | 0.436 / 0.411 | 8 / 159, 8 / 188 |
| italian_flat camera 1024 x 1024 (lit) | 39 / 389 / 413 | 19 / 116 / 131 | 0.45 / 0.68 / 0.83 / 0.95 | 0.419 / 0.427 | 9 / 300, 7 / 86 |
| italian_flat camera 1920 x 1080 (lit) | 9 / 361 / 415 | 12 / 107 / 124 | 0.67 / 0.85 / 0.91 / 0.98 | 0.705 / 0.563 | 6 / 242, 5 / 83 |

### Field, in voxels

| case | box x / y / z median | box x / y / z 99th | distinct median / 99th / most | items at most 64 / 128 / 256 / 512 / 1024 | share read median / mean | cells an item median / 99th / most | cells a row median / 99th | rows with 1 / <= 2 / <= 4 cells |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sponza overview 1024 x 1024 (gi) | 4 / 3 / 3 | 25 / 10 / 10 | 26.5 / 104 / 147 | 0.89 / 1.00 / 1.00 / 1.00 / 1.00 | 0.815 / 0.691 | 6 / 31 / 52 | 3 / 11 | 0.11 / 0.41 / 0.75 |
| sponza overview 1920 x 1080 (gi) | 3 / 3 / 3 | 25 / 9 / 10 | 18 / 68 / 89 | 0.98 / 1.00 / 1.00 / 1.00 / 1.00 | 0.917 / 0.782 | 4 / 19 / 26 | 2 / 8 | 0.25 / 0.62 / 0.88 |
| bistro_interior overview 1024 x 1024 (gi) | 3 / 3 / 4 | 30 / 11 / 46 | 30 / 226 / 290 | 0.73 / 0.90 / 1.00 / 1.00 / 1.00 | 0.875 / 0.704 | 8 / 70 / 91 | 3 / 13 | 0.10 / 0.43 / 0.75 |
| bistro_interior overview 1920 x 1080 (gi) | 3 / 3 / 4 | 30 / 10 / 44 | 30 / 150 / 213 | 0.82 / 0.97 / 1.00 / 1.00 / 1.00 | 0.833 / 0.696 | 7 / 45 / 70 | 3 / 10 | 0.21 / 0.49 / 0.79 |
| modern_hall overview 1024 x 1024 (gi) | 6 / 4 / 4 | 65 / 34 / 23 | 53.5 / 358 / 622 | 0.58 / 0.83 / 0.96 / 0.99 / 1.00 | 0.789 / 0.669 | 15 / 129 / 207 | 4 / 18 | 0.03 / 0.21 / 0.59 |
| modern_hall overview 1920 x 1080 (gi) | 5 / 3 / 3 | 57 / 16 / 22 | 38 / 238 / 328 | 0.76 / 0.95 / 0.99 / 1.00 / 1.00 | 0.867 / 0.707 | 10 / 68 / 90 | 3 / 17 | 0.04 / 0.35 / 0.80 |
| bistro_exterior overview 1024 x 1024 (lit) | no field | | | | | | | |
| bistro_exterior overview 1920 x 1080 (lit) | no field | | | | | | | |
| italian_flat camera 1024 x 1024 (lit) | no field | | | | | | | |
| italian_flat camera 1920 x 1080 (lit) | no field | | | | | | | |

### Textures, in texels of a level

| case | pairs median / 99th / most | pairs within 32 / 64 / 128 squared (pooled) | an item's share within 32 / 64 / 128 (mean) |
| --- | --- | --- | --- |
| sponza overview 1024 x 1024 (gi) | 6 / 19 / 33 | 0.55 / 0.79 / 0.89 | 0.46 / 0.74 / 0.84 |
| sponza overview 1920 x 1080 (gi) | 4 / 15 / 22 | 0.46 / 0.72 / 0.86 | 0.36 / 0.68 / 0.83 |
| bistro_interior overview 1024 x 1024 (gi) | 2 / 29 / 51 | 0.55 / 0.82 / 0.95 | 0.36 / 0.75 / 0.93 |
| bistro_interior overview 1920 x 1080 (gi) | 2 / 29 / 61 | 0.53 / 0.78 / 0.91 | 0.50 / 0.78 / 0.91 |
| modern_hall overview 1024 x 1024 (gi) | 2 / 5 / 6 | 0.29 / 0.50 / 0.77 | 0.23 / 0.41 / 0.76 |
| modern_hall overview 1920 x 1080 (gi) | 1 / 5 / 5 | 0.30 / 0.51 / 0.70 | 0.23 / 0.44 / 0.68 |
| bistro_exterior overview 1024 x 1024 (lit) | 7 / 42 / 69 | 0.63 / 0.83 / 0.96 | 0.63 / 0.84 / 0.96 |
| bistro_exterior overview 1920 x 1080 (lit) | 8 / 33 / 53 | 0.53 / 0.76 / 0.90 | 0.50 / 0.77 / 0.91 |
| italian_flat camera 1024 x 1024 (lit) | 4 / 31 / 34 | 0.79 / 0.91 / 0.98 | 0.43 / 0.76 / 0.97 |
| italian_flat camera 1920 x 1080 (lit) | 3 / 34 / 38 | 0.76 / 0.85 / 0.96 | 0.42 / 0.59 / 0.92 |


## A core's working set

The distinct pages a core reads in one frame over all its items (the union of its
passes' pages; textures over every layer), median and most over the 120 cores.

| case | textures median / most | shadow median / most | field median / most |
| --- | --- | --- | --- |
| sponza overview 1024 x 1024 (gi) | 328.5 / 827 | 32 / 58 | 25 / 41 |
| sponza overview 1920 x 1080 (gi) | 392 / 777 | 40 / 59 | 34 / 48 |
| bistro_interior overview 1024 x 1024 (gi) | 152 / 246 | 41 / 75 | 42 / 69 |
| bistro_interior overview 1920 x 1080 (gi) | 262 / 363 | 58 / 93 | 60.5 / 94 |
| modern_hall overview 1024 x 1024 (gi) | 36 / 78 | 38 / 68 | 52 / 98 |
| modern_hall overview 1920 x 1080 (gi) | 52 / 86 | 53 / 84 | 72 / 108 |
| bistro_exterior overview 1024 x 1024 (lit) | 276.5 / 408 | 26 / 50 | - |
| bistro_exterior overview 1920 x 1080 (lit) | 504.5 / 680 | 33.5 / 53 | - |
| italian_flat camera 1024 x 1024 (lit) | 39 / 105 | 38.5 / 71 | - |
| italian_flat camera 1920 x 1080 (lit) | 76.5 / 173 | 39 / 57 | - |
