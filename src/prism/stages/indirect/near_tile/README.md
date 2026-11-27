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
| `host.py` | `NearTileHost`: with the pipeline's option `near_tile` (False by default), `W_T` built by the reference when a camera is asked twice in a row and is not the one built (`near_tile_workers` processes), written into the tensor of slot `near.weights`; without it, nothing |
| `model/weights.py` | the records: a screen tile's 8 bfp8_b tiles (tile k the half rows 2k and 2k + 1 of the tile's 16 x 16 half pixels, a half pixel a row, its 32 columns), the screen's tiles row by row; encoded and decoded by Komorebi's formats |
| `model/build.py` | a view's records built by the reference (`near/view.py`: the frame, the march at half resolution, `W_T`) |

## The records

A frame of 1,920 x 1,080 has 60 x 34 screen tiles; a record is 8,704 bytes, the tensor
17.8 MB. Its values are the reference's `W_T` in bfp8_b as Komorebi's encode writes it:
16 consecutive numbers of a tile's row (a half pixel's columns 0 to 15, then 16 to 31)
share their exponent.

## Checking

`python -m checks.near_tile --scene sponza --view overview --size 1920 1080 --workers 8
--card 1`: the records of the near field check's written scene and of the view written
into a tensor and read back, bytes and values against the host's encode and decode.
