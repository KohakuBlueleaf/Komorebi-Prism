# indirect.near_tile

The near and far fields of the indirect light as one product a screen tile,
`E = W_T . S_T` (the reference: `prism_reference/indirect/near/one_tile.py`, the form in
[near field](../../../../../docs/internals/reference/near_field.md), section "One
tile", the blended form of "The blend across tiles": a half pixel's row reads the
operands of the 2 x 2 tiles around it). `W_T` depends on the geometry and the eye only:
it is built for a camera that stands and held in the card's memory; `S_T` follows the
light.

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | the declaration (`NEAR_TILE`), registered as `indirect.near_tile` |
| `host.py` | `NearTileHost`: with the pipeline's option `near_tile` (False by default), `W_T` built by the reference when a camera is asked twice in a row and is not the one built (`near_tile_workers` processes); its blocks written into the tensor of slot `near.weights`, the tables, `S_T` a tile (a bfloat16 tile, the operand) and the upsample's weights (a page a quarter tile) into their tensors (written live, made at the frame's size before the load); the unit's numbers `near_weights`, `near_operand`, `near_upsample`, `near_table`, `near_half` (the frame's half columns and rows), `near_on`; refused unless the tile thread is `GI_NEAR`; without it, nothing |
| `model/operand.py` | `S_T` as the card holds it (bfloat16): the cells' means of the frame's lit radiance, the far groups of the field's packed values, the ambient; its tiles' pages; `E` on a tile's plane from the blocks' values and the table (the host's form of the product) |
| `steps/` | the step `near_tile` of the tile thread `GI_NEAR`: the tile's table asked, then each row block's W tiles and operands, `E` made on the matrix engine into the plane `near.light`, marked on; the light step `LIGHT_NEAR` then takes a row's `I` from it (`direct/light/steps/kernels/near_rows.hpp`) in place of the field lookup |
| `thread/` | the unit's header and the step's frame words (the four tensors' addresses, the frame's half size, on) |
| `model/regions.py` | the blended `W_T` by region: a tile's plane (its 16 x 16 half pixels and one more row and column, 17 x 17) put into row blocks of 32 half pixels that read one operand each (a half pixel in pieces when it reads more), a bfp8_b tile an operand; the table a tile |
| `model/weights.py` | the blocks (32 a tile at most, the screen's tiles row by row) and tables of a view; encoded and decoded by Komorebi's formats |
| `model/build.py` | a view's records built by the reference (`near/view.py`: the frame, the march at half resolution, `W_T`) and the upsample's weights (`near/half.py` `upsample_weights`) |

## The records

A half pixel of the blended form reads the operands of the 2 x 2 tiles around it, among
the 3 x 3 around its own tile; a tile's plane also holds the row and column after it,
since the upsample of its last pixels reads them. The host puts the plane's half pixels
into row blocks of 32 that read one operand each (`regions.packed` with `most` 1): a
half pixel reading 2 or 4 tiles is split into a piece a tile (its E the sum of theirs),
the pieces grouped by their tile. A tile with the whole frame around it has 26 blocks
of 26 W tiles (64 half pixels read only their own tile, 144 two, 81 four); its W is
28.3 KB in bfp8_b (the form alone: 8 tiles, 8.7 KB). The tensor keeps 32 tiles a screen tile
(71.0 MB at 1,920 x 1,080). The table of a tile (`near_tile_step.h`) gives each block
its operands, its first W tile, the operands' tiles and the plane place of each of its
rows.

The values are the reference's `W_T` in bfp8_b as Komorebi's encode writes it: 16
consecutive numbers of a tile's row share their exponent.

## On the card, this step

With the option on and the camera standing, the pack CPU asks the tile's table into the
plane, zeroes the plane's `E`, writes its size and the upsample's tensor address and
marks the table with the count of tiles it has done; the other two compute CPUs read the
table once that count reaches theirs. For each block the pack CPU asks its W tiles into
the ring `w` (bfp8_b) and its operand into the ring `s` (bfloat16), one place each; the
unpack CPU serves the asks' mails. The three compute CPUs make the block's `E` on the
matrix engine (unpack, math and pack: `matmul_block` of W's tile k by S's tile k into
Dst, k over the block's operands, float32 accumulation at HiFi4), the pack CPU packs it
into the ring `e` (float32) and adds the three channels of each row at its place in
the plane. Dst is zeroed before the first product: the products add into Dst, and the
light step leaves it holding its scratch.

The light step asks the upsample's weights a quarter tile at a time (8 rows, 4 KB)
into the plane before it lights that quarter, into the page that held the table while
this step ran; the plane is 8 KB. The light step's `I` of a pixel is then the sum over its four
taps of the upsample's weight times `E` at the tap's half pixel (in the plane, also the
row and column after the tile), in float32 (a fused multiply-add a tap, the taps in the
order (0, 0), (0, 1), (1, 0), (1, 1)). On any other frame the light step does the
field's lookup. A glass surface's own light keeps the lookup.

Its cost, standing, at 1,920 x 1,080 on one base: Sponza's overview 13.78 ms a frame
against 12.34 ms for the form alone (+1.44 ms, the price of the blend across tiles),
italian_flat's camera 27.2 ms against 24.7 to 25.5 ms. Two operands a block would save
0.5 ms a frame (14 blocks of 27 W tiles against 26 of 26), and need 3,136 B more of
rings (a second place of `w` and of `s`).

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
