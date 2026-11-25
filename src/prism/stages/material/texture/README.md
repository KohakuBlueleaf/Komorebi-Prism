# material.texture

SHADE on the card: every pixel FILL left in a layer's frame gets its material's colour.
For a textured material that is the albedo texel at the pixel's u, v, read from the
scene's texture pages. Each core works through its part of the raster stage's directory
and lists, one item at a time, on the same 32 x 32 tiles FILL wrote. The forms: the
opaque layer; the masked layer merged into the opaque one, with or without the merged
1/z; the glass layer blended over it. The lit forms (a camera given) write the layer's
surface instead of colour: its material word and 1/z to the frame and the surface's two
frames of planes (normal, specular, albedo and the rest) for the direct-light stage; the
masked layer merged into the opaque frame and surface; the glass layer's own surface.

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | the implementation `material.texture`: fills `material`, reads `frame.visibility` and `frame.lists`, writes `mesh.attributes` and `frame.surface` |
| `device.py` | `Shade`, the class on the card: one `km.kernel` handler `shade`, its own fields and the common ones (`prism.core.fields`; the surface's directory words in the common pages `own_page_1`, `own_page_2`: `kDirA`, `kDirB` in `kernels/mover_a/directory.hpp`); the frame program's compute set; `made(host)` |
| `host.py` | `TextureHost`: the textures and SHADE's table tensors, a shade-block tensor and a profile a layer, with `lights` the lit tensors (each written surface's two frames and directory, `surface(layer)`); `slots()` (`mesh.attributes`), `connect()` (the raster stage's `frame.lists` and `frame.visibility`), each layer's row (`thread_layer`, `view`), `picture()` (the frame's colour as the 8-bit picture), `words()`, `MODES` |
| `unit.py` | the thread unit: the layer role, SHADE's words as the layer's columns (SHADE's table shared with slot `mesh.attributes`), slot `frame.lists` taken (a DEPTH view's directory and lists), its time `shade` |
| `thread/material_texture_unit.c` | a layer's SHADE from its columns (none when its directory is 0), lit when its surface column is set; a DEPTH view's masked merge from the view's own directories; its time the layer's |
| `check/thread_frame.py` | the preset `textured`'s frames by a Loop: the first and last pictures against the reference, the codes, the times by layer |
| `check/frame.py` | a shaded frame stepped by the host, the raster and texture classes alone, against the reference (`model/expect.check`) |
| `model/` | the host side as numpy: the layers, the table, the texture pages, the shaded materials |
| `kernels/shade.h` | SHADE's constants: handler, mode bits, the profile's words; a last section of LIGHT's constants |
| `kernels/waits.hpp` | the compute threads' waits from the command's control word |
| `kernels/unpack.hpp` | the unpack thread: the pack thread's mails served |
| `kernels/mover_a/` | the directory pages (lit: the surface's frame words), the table (lit: the camera after it), an item's list pages and planes (lit merging: the opaque surface's two parts after them), the texel pages asked (`reader.hpp`, the polled step loop) |
| `kernels/mover_b/writer.hpp` | the out items to the frame's planes (lit: three parts, the frame's and the surface's two frames), the profile to the core's page |
| `kernels/pack/` | the pack thread: planes into Dst, u, v and light divided by 1/z, the records' keys, the page passes and texels, colour, merge or blend, the profile; `list.hpp` the list pages read in order |
| `kernels/pack/lit/` | the lit form on the pack thread: a pixel's winner and its slot (`winners.hpp`, `slot.hpp`), the records' three keys (`records.hpp`), the page passes (`texels.hpp`), the surface planes (`surface.hpp`), the merge (`merge.hpp`), the command (`lit.hpp`) |

Shared with other stages, in `src/prism/core/include/`: `surface.h` (the texture page,
the material word, the surface planes), `texel_pages/` (the ask and done pages, the page
passes, the gather), `compute_mail.hpp` (the pack thread's waits served by the unpack
thread), `sfpu.hpp` (the vector unit's registers, arithmetic and thread state).

## The command

`shade(directory, lists, textures, table, profile, opaque, mode, grid, camera, surface)`.
The layer's directory and lists come from the raster stage. `opaque` is the opaque
layer's directory when merging, else 0. `mode` holds the kShade* bits (glass, merged
depth). `grid` is the frame's grid word (lit: the camera's bank in it, grid.h's a8).
`camera` is the camera's address in that bank, 0 for the unlit forms; `surface` is the
surface directory the lit form writes (merging: the opaque layer's), any tensor when
unlit. The slots, the pack thread's work and the page passes' hash are the parts of the
common field `command_space` it lays with LIGHT (layout `texel`, `prism.core.fields`;
each part's address from `core/include/texel_pages/space.hpp`); the other stages lay
theirs over the same bytes, each within its commands.

## In the frame's thread

The preset `textured` (`configs/pipeline/textured.py`) is the raster stage, then this
one. The director calls the raster unit for every layer of the frame (each layer's
SETUP the shaded one, with its shade blocks), then this unit for every layer: SHADE of
the opaque layer, the masked one merged into it (with the merged 1/z when a glass layer
follows), the glass one blended over it. The host writes each layer's columns: the
raster stage's directory and lists of that layer (slot `frame.lists`), the textures,
the table, the layer's profile, the opaque layer's directory when it merges, the mode,
and the layer's surface directory (0 when unlit). The unit's C reads them and builds
the command with its class's builder.

In the preset `lit` the host is given the option `lights` and makes each written
surface (the lit tensors), and gives each layer's surface directory as slot
`frame.surface` (the masked layer's the opaque one's) to the direct-light stage, which
writes LIGHT's words into those pages. A layer's surface column set makes the unit's
SHADE the lit form: the camera the view's (`camera_at`, its bank in the grid word), the
surface the layer's; the lit masked layer merges into the opaque frame and surface
without the merged-1/z bit, the lit glass layer writes its own surface (no opaque
directory). Unlit, the camera is 0 and the surface word is the layer's directory (any
tensor).

A DEPTH view (the sun's pass) gets only the masked layer's merge of its 1/z into the
opaque layer's, in the lit form with mode 0: the view's
own directory and lists (slot `frame.lists`, the raster unit's columns of that view's
rows), the opaque row's directory of the same view, the view's camera, the opaque
surface as scratch. Nothing for the opaque layer, and nothing without a surface.

## Checks

`python scripts/run/texture_frame.py --scene <scene> --view overview` runs a whole shaded
frame by the classes against the reference's picture. `python scripts/run/preset.py
--pipeline textured --scene <scene> --view overview --size 1024 1024` runs the preset's
frames by the thread (`check/thread_frame.py`).
