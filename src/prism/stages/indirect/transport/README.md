# indirect.transport

The far field of indirect light: one apply `y = M x` of a scene's light-transport matrix,
stored as a hierarchical (block low-rank) matrix, on every core of the card as one
command. `x` is every element's outgoing light (`elements.radiance`), `y` the light each
element receives (`elements.irradiance`). It fills the item `indirect`.

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | the declaration (`TRANSPORT`), registered as `indirect.transport` |
| `device.py` | `Apply`, the class on the card: one handler `apply`, a `km.kernel` handler; its frame form (`joined`, `window_defines`, `windows_bytes`: its windows against the command space); `made(host)` |
| `host.py` | `TransportHost`: the set (the scene's, or the view's scene with the option `name`), its sizes, the tensors, w's cache, the option `compute` |
| `unit.py` | the thread unit: gives `elements.irradiance` (`indirect_transport_unit_pass`, one apply), serves `apply`, its number `transport_cores`, its results region (a part of the director's numbers region, `own=False`) |
| `kernels/apply_window.hpp` | the frame form's windows: their layout in `command_space`, its `static_assert`, each CPU's views placed and set back |
| `thread/indirect_transport_unit.c`, `.h` | the pass: APPLY built by the class's builder, run, its ticks, count and code kept |
| `check.py` | y against the emulation and against the set's float result; a command's time |
| `plan/set.py` | a set's files (`blocks.npz`, `weights.f32`, the vectors) |
| `plan/deal.py` | the receiver tiles dealt to the cores in contiguous ranges |
| `plan/tables.py` | each core's table of entries, in pages of 4 KiB |
| `plan/weights.py` | w's pages laid out, encoded in bfp8_b (tiles stored transposed), decoded |
| `plan/emulate.py` | x's tiles, bfloat16 rounding, the apply emulated on the host |
| `plan/sizes.py` | the sizes a core's buffers are made for |
| `kernels/apply.h` | a table page's and an entry's words, the reads' pattern, shared helpers |
| `kernels/apply_reader.hpp` | mover A: the table pages, its share of x's and w's streams |
| `kernels/apply_writer.hpp` | mover B: its share of the streams, y's tiles and the profile page |
| `kernels/apply_compute.hpp` | the products onto the own sums, y's pages, the stamps |

## The set

A set is the folder `<data root>/public/<scene>_transport/` (`PRISM_DATA` names the data
root); its own `README.md` gives the layout. The encoded w is kept under
`<cache root>/apply/<scene>_<key>.npy` (`PRISM_CACHE`, else `<data root>/cache`), the key
made of the set's `blocks.npz` and `weights.f32` sizes and times, the cores and the
encoding.

## The class

`Apply`'s constants `OWN`, `KMAX`, `RANK`, `PAGES`, `BLOCK` are given at the make from the
set's sizes. x and w stream through the pairs `x_in` and `w_in`; every other buffer is an
own field, whole: the sums, t, the token, y's pages, the profile page (`apply_profile`),
the table and head pages of each mover. Mover B's two are the common pages `own_page_1`
and `own_page_2`, defined once in `prism.core.fields` for every class that uses them
(each uses them only inside its own command); `kernels/apply.h` names them `kTableB` and `kHeadB`. The
kernels name the rest by the class header's names (`kPairXIn`, `kFieldSums`,
`kConstKmax`, ...).

Alone (the presets `apply`, `field`), the class is as above, with its own compute set
(HiFi2). In a frame program (the pipeline's option `compute`) it is made in its frame
form (`joined`): that program's set (`prism.core.compute.FRAME_COMPUTE`: HiFi4, float32
in Dst, its float32 fields unpacked to Dst as the class form does for its own), the
common field `command_space` (`prism.core.fields`: the space each stage lays its
parts in for the length of a command, sized at the frame's capacity `held` by the
largest stage's parts, not by this set), and x's and w's pairs, the sums, t, the token
and y's
pages declared one page each. At the start of a command each CPU but math points those
buffers' views at windows over the whole of `command_space`,
their pages as the class alone has them (`window_defines`: the set's sizes and the
formats' page bytes), end to end on 64 bytes (`kernels/apply_window.hpp`); at its end
it sets the views' places back (the pages counted stay). A set whose windows do not
fit the space is refused at the make, naming both numbers (`windows_bytes`; the
kernels' `static_assert` too). What the other stages lay there lives within their
commands (`prism.core.fields`, beside `LAYOUTS`).

## Running

```bash
python scripts/run/apply.py --scene sponza --calls 32
```

The preset `apply` (`configs/pipeline/apply.py`) runs this implementation alone. The
numbers go to `measurements/apply/`.
