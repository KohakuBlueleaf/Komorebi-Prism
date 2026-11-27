# indirect.near_tile

The near and far fields of the indirect light as one product a screen tile,
`E = W_T . S_T` (the reference: `prism_reference/indirect/near/one_tile.py`, the form in
[near field](../../../../../docs/internals/reference/near_field.md), section "One
tile"). `W_T` depends on the geometry and the eye only: it is built for a camera that
stands and held in the card's memory; `S_T` follows the light.

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | the declaration (`NEAR_TILE`), registered as `indirect.near_tile` |
| `host.py` | `NearTileHost`: with the pipeline's option `near_tile` (False by default), `W_T` built by the reference when a camera is asked twice in a row and is not the one built (`near_tile_workers` processes); its records written into the tensor of slot `near.weights`, `S_T` a tile (a bfloat16 tile, the operand) and the upsample's weights (a page a quarter tile) into their tensors (written live, made at the frame's size before the load); the unit's numbers `near_weights`, `near_operand`, `near_upsample`, `near_half` (the frame's half columns and rows), `near_on`; refused unless the tile thread is `GI_NEAR`; without it, nothing |
| `model/operand.py` | `S_T` as the card holds it (bfloat16): the cells' means of the frame's lit radiance, the far groups of the field's packed values, the ambient; its tiles' pages; `E` a tile from the records' values (the host's form of the product) |
| `steps/` | the step `near_tile` of the tile thread `GI_NEAR`: the tile's record, `S_T` and page of the upsample's weights asked, `E = W_T . S_T` made on the matrix engine into the plane `near.light`, marked on; the light step `LIGHT_NEAR` then takes a row's `I` from it (`direct/light/steps/kernels/near_rows.hpp`) in place of the field lookup |
| `thread/` | the unit's header and the step's frame words (the three tensors' addresses, the frame's half size, on) |
| `model/weights.py` | the records: a screen tile's 8 bfp8_b tiles (tile k the half rows 2k and 2k + 1 of the tile's 16 x 16 half pixels, a half pixel a row, its 32 columns), the screen's tiles row by row; encoded and decoded by Komorebi's formats |
| `model/build.py` | a view's records built by the reference (`near/view.py`: the frame, the march at half resolution, `W_T`) and the upsample's weights (`near/half.py` `upsample_weights`) |

## The records

A frame of 1,920 x 1,080 has 60 x 34 screen tiles; a record is 8,704 bytes, the tensor
17.8 MB. Its values are the reference's `W_T` in bfp8_b as Komorebi's encode writes it:
16 consecutive numbers of a tile's row (a half pixel's columns 0 to 15, then 16 to 31)
share their exponent.

## On the card, this step

With the option on and the camera standing, the pack CPU asks the tile's record in two
halves of 4 tiles into the step's ring `w` (bfp8_b) and its `S_T` into the ring `s`
(bfloat16), and writes the upsample's tensor address into the plane; the unpack CPU
serves the asks' mails. The three compute CPUs then make `E` a record tile at a time on the
matrix engine (unpack, math and pack: `matmul_block` of W's tile k by S into Dst, float32
accumulation at HiFi4), the pack CPU packs it into the ring `e` (float32) and copies its
three columns into the plane, half rows 2k and 2k + 1. Dst is zeroed before the first
product: the products add into Dst, and the light step leaves it holding its scratch.

The light step asks the upsample's weights a quarter tile at a time (8 rows, 4 KB)
into the plane before it lights that quarter, so the plane holds E and one quarter's
weights (8 KB). The light step's `I` of a pixel is then the sum over its four taps of the upsample's
weight times `E` at the tap's half pixel, in float32 (a fused multiply-add a tap, the
taps in the order (0, 0), (0, 1), (1, 0), (1, 1)). On any other frame the light step
does the field's lookup. A glass surface's own light keeps the lookup.

## The state of a moving frame

`W_T` is built by the reference on the host: a camera that moves is lit by the field's
lookup, and a camera that stops waits for the host's build before its near field
returns: at 1,920 x 1,080 on 8 processes, 22.5 s on Sponza's overview (the frame's
reference 15.2 s, the operator 7.3 s) and 58.7 s on italian_flat's camera (51.2 s and
7.5 s). `S_T` is also made on the host from the
frame the reference lights. Building `W_T` on the card (the march with the cells'
credit, a share of the tiles a frame) is the piece that removes the wait.

## Checking

`python -m checks.near_tile --scene sponza --view overview --size 1920 1080 --workers 8
--card 1`: the records of the near field check's written scene and of the view written
into a tensor and read back, bytes and values against the host's encode and decode.
