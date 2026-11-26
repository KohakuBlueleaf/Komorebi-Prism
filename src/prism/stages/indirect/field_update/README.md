# indirect.field_update

The indirect light field made again after a light change, on the card's X280 thread: from
the sun's shadow map and the scene's elements, each element's sky, sun and first light L0;
the bounce passes `E_p = M x` (each the apply of the unit that gives
`elements.irradiance`); `e = E_1 + ... + sky`; the field's values by row; its scale and its
texels (a has-data bit, three square-root codes); its pages stored where LIGHT reads them.
One thread command `update` does it all, or in steps. It has no class of its own: it
is a thread unit and a host. It reads `elements.irradiance`, `elements.radiance` (the
passes' x is stored there) and `light.shadow_map`, and writes `light.field`.

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | the declaration (`FIELD_UPDATE`), registered as `indirect.field_update` |
| `unit.py` | the unit: its sources, the command `update`, the slot it takes, its six regions, its numbers, the header's word places as defines |
| `host.py` | `FieldUpdateHost`: the lights at the sun, the field model, the light pages, the regions' contents, the numbers, the sun's words written live, the steps run, the field read back |
| `check.py` | the update against the reference: the texels, the scale and units, sky and L0, the codes, the times, the verdict (codes 0; the field's code difference at most 1 at 0 bounces or stepped, at most 12 whole with passes: the card applies the matrix in its tile formats, and the largest difference recorded is 10 of 255) |
| `model/numbers.py` | the C header's numbers, the header region's words and places, the numbers it asks for |
| `model/regions.py` | the operator by row, each row's place in the pages, the elements' arrays and region, the counts, the work region's layout |
| `model/header.py` | the header region's words and the sun's words |
| `model/results.py` | the times rows, the work region's arrays, the field's texels, the reference's numbers (`expected`) |
| `thread/indirect_field_update.h` | the sizes, the times row's words, the steps, the codes |
| `thread/indirect_field_update_unit.c`, `.h` | the command's steps: the job taken, the sources, a pass, the finish, the step switch |
| `thread/indirect_field_update_parts.c` | the parts on the four X280 cores and their math |

## The command

`update` takes its step in `a0`: 0 the whole update, 1 the sources (through pass 1's x
stored into x's tensor), 2 a pass (y fetched and added, the next x stored), 3 the finish
(the rows, the scale, the texels, the pages stored). With steps the host runs the apply
between 1, 2 and 3 (the stepped form, `run(stepped=True)`); step 0 calls
`DR_GIVE_ELEMENTS_IRRADIANCE` for each pass. Each command adds its parts' ticks to the
update's row in the region `field_times` (16 rows of 32 words, `FU_T_*`); the row tells
the first three passes apart (`FU_T_PASS_APART`), a later pass adds into the third's
words (`model/results.py` `times`: that entry's `summed`).

## Regions and numbers

| region | holds |
| --- | --- |
| `field_header` | the counts, the arrays' offsets, the sun's words (`model/numbers.py` `HEADER`); a part of the director's numbers region (`own=False`) |
| `field_elements` | position, normal, base, albedo / pi, transfer; the operator's row starts and pairs; each row's place |
| `field_shadow` | the shadow map's pages, fetched from the light pages |
| `field_work` | sky, L0, the total, x's and y's tiles, the rows' values |
| `field_pages` | the field's pages before they are stored |
| `field_times` | the update's times rows |

The numbers (`update_*`) are the light pages' address with the shadow map's and the
field's first pages, the addresses of x and y (the tensors of `elements.radiance` and
`elements.irradiance`, found by slot) and the cores that copy.

## In a loop, and what LIGHT takes

The light pages are slot `light.field`'s tensor when a host gives it (the light host),
else the update's own. In a loop the host asks for `update` (`commands()`, the whole
form, the option `bounces`) whenever the run's option `sun` differs from the sun its
field was made for: it writes the sun's words of the lights at that sun first (the
light stage's `sun_lights`; the shadow map the card's own, drawn by the `sun` command
sent before it). `update` writes no director row (`Command(row=False)`). When it comes
back 0, the host sends `field_scale`, which returns the last finished update's scale as
its float32's word, and gives it in slot `light.field_scale` (the updates made, the
scale). The light host takes that slot and writes LIGHT's table itself, the three units
(1 / max code)^2 x scale computed from the scale as the card computes them; the unit
writes nothing into another unit's region (`FU_T_TABLE` stays 0). The scale and the
units are still in the times row (`FU_T_SCALE`, `FU_T_UNIT`) for the record after the
stop. A failed update sends nothing, and the table stays as it was.

## Beside the frames (the option `update_beside`)

With the build option `update_beside` (the preset `gi_tile`) this unit and
`indirect.transport`'s run on work cluster 2 (`prism.core.unit.BESIDE`), a thread of
their own with the director's runtime, their regions and numbers in that cluster's
bank, written by their hosts as on cluster 1. Frames go on while the update runs:

- The host marks `update` `beside=True`: the loop submits it to cluster 2 and does not
  wait; before each frame it looks for its event (never waiting), and once it came the
  host's `served` sends `field_scale` and the light host writes LIGHT's table, before
  that frame. A sun change while an update runs is taken when the running one is served.
- Only the frame's director (cluster 1) submits commands to the cores: the program's
  depth is 1, and the raster keeps a part of the command space between two of its
  commands of one layer, so a core command of another source must not land between
  them. On cluster 2 `dr_submit` sends the core command as the director's command
  `core_step` (its header, group and words a0 to a7); the director runs it between two
  commands and answers its code and its own time. Each such step is a row of cluster 2's
  times region (`Loaded.steps`). `kmx_fetch` and `kmx_store` are the exception: they
  copy through the run's transfer buffer, touch no field of the program, and must be
  called by the thread whose region they move, so cluster 2 calls them itself. While
  one holds the program's one slot, the director's next core command is rejected busy:
  the director submits it again at the dispatcher's wake, within its wait limit, and
  counts it in the times row's `resubmits`.
- The light pages hold the field's pages twice: the half LIGHT reads and the half the
  update writes (`update_field_first`, the other half). The light host's table write
  with the new scale, units and the new half's first page (`kLtFieldFirst`) is the
  swap; the halves then change roles. The first field, made at load, is in the first
  half.

## Running

```bash
python scripts/run/field.py --scene sponza --bounces 2 [--stepped]
```

The preset `field` (`configs/pipeline/field.py`) runs `indirect.transport` and this
implementation. The records go to `measurements/field_update/`.
