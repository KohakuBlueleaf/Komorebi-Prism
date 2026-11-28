"""The blended W as the card holds it, by region: a screen tile's half pixels with the
apron (SIDE x SIDE from its corner) put into row blocks of 32 that read at most `most`
tiles' operands, each block's W a bfp8_b tile per operand; and a table page a tile. A
half pixel reading more tiles is split into pieces, its E the sum of theirs."""

from functools import cache

import numpy as np

from prism_common.formats import TILE
from prism_reference.scene.frame import frame_grid

SKIP = 0xFFFF  # a row of a block that is no half pixel
ENTRY_WORDS = 20  # a row block's words in the table
PLACES_AT = 4  # its places' first word


def pixel_classes(w, owners, tile, side):
    """For every screen tile and place of its SIDE x SIDE plane: the half pixel's row
    (y, x) or -1 past the frame, and its 9-bit mask of the 3 x 3 neighbouring tiles
    (dy + 1) x 3 + dx + 1 whose rows are not all 0; (down, across, side, side) each."""
    h, wd = w.shape[:2]
    across, down = -(-wd // tile), -(-h // tile)
    ty, tx = np.mgrid[0:down, 0:across]
    py, px = np.mgrid[0:side, 0:side]
    y = ty[:, :, None, None] * tile + py
    x = tx[:, :, None, None] * tile + px
    inside = (y < h) & (x < wd)
    yc, xc = np.minimum(y, h - 1), np.minimum(x, wd - 1)
    mask = np.zeros(y.shape, np.int64)
    for c in range(len(owners)):
        used = np.any(w[yc, xc, c] != 0, -1) & inside
        dy = owners[c][0][yc, xc] - ty[:, :, None, None]
        dx = owners[c][1][yc, xc] - tx[:, :, None, None]
        mask |= np.where(used, 1 << ((dy + 1) * 3 + dx + 1), 0)
    return np.where(inside, y, -1), np.where(inside, x, -1), mask


def pieces(mask, most):
    """A pixel's mask as pieces of at most `most` tiles: its tiles in the 3 x 3's order,
    `most` at a time."""
    bits = [b for b in range(9) if mask >> b & 1]
    return [sum(1 << b for b in bits[i : i + most]) for i in range(0, len(bits), most)]


def packed(counts, most):
    """Row blocks of the piece masks `counts` ({mask: rows}): each block at most 32 rows
    and `most` tiles, the masks largest first into the block they add least to; a list
    of [mask of the block, [(mask, rows), ...]]."""
    blocks = []
    for mask in sorted(counts, key=lambda m: (-m.bit_count(), m)):
        left = counts[mask]
        while left > 0:
            best = None
            for block in blocks:
                rows = sum(n for _, n in block[1])
                union = block[0] | mask
                if rows < TILE and union.bit_count() <= most:
                    cost = union.bit_count() - block[0].bit_count()
                    if best is None or cost < best[0]:
                        best = (cost, block, rows)
            if best is None or best[0] >= mask.bit_count():
                best = (0, [0, []], 0)
                blocks.append(best[1])
            take = min(left, TILE - best[2])
            best[1][0] |= mask
            best[1][1].append((mask, take))
            left -= take
    return blocks


def region_records(w, owners, size, form):
    """The blocks (tiles x most_blocks, 32, 32) float32 and the tables (tiles,
    table_words) uint32 of the blended W (H, W, 4, WIDTH) and its owners (4, 2, H, W)
    at half rows, a frame of `size`; `form`: tile, side, most, most_blocks, table_words.
    """
    across, down = frame_grid(size)
    ys, xs, masks = pixel_classes(w, owners, form["tile"], form["side"])
    per = form["most_blocks"]
    blocks = np.zeros((down * across * per, TILE, w.shape[-1]), np.float32)
    tables = np.zeros((down * across, form["table_words"]), np.uint32)
    for ty in range(ys.shape[0]):
        for tx in range(ys.shape[1]):
            t = ty * across + tx
            plane = (ys[ty, tx], xs[ty, tx], masks[ty, tx])
            made, rows = tile_blocks(w, owners, (ty, tx), plane, form["most"])
            if len(made) > per or 1 + ENTRY_WORDS * len(rows) > form["table_words"]:
                raise ValueError(
                    f"tile {t}: {len(made)} blocks of {per}, {len(rows)} row blocks of "
                    f"{(form['table_words'] - 1) // ENTRY_WORDS}"
                )
            blocks[t * per : t * per + len(made)] = made
            tables[t] = table_page(rows, t * per, across, (ty, tx), form)
    return blocks, tables


@cache
def piece_table(most):
    """pieces(mask, most) of every 9-bit mask (512,), each a tuple."""
    return tuple(tuple(pieces(mask, most)) for mask in range(512))


def tile_blocks(w, owners, at, plane, most):
    """One tile's W blocks (n, 32, WIDTH) and its row blocks [(operands [(dy, dx)],
    first block, places (32,) as SIDE x y + x or SKIP)]."""
    ys, xs, mask = plane
    side = mask.shape[0]
    p_y, p_x = np.nonzero(mask)
    masks = mask[p_y, p_x]
    table = piece_table(most)
    # piece mask: the plane places holding it (indices into p_y), in order
    by_piece = {}
    for m in np.unique(masks):
        for piece in table[int(m)]:
            by_piece.setdefault(piece, []).append(np.flatnonzero(masks == m))
    by_piece = {k: np.sort(np.concatenate(v)) for k, v in by_piece.items()}
    # each place's owners' offsets (dy + 1) x 3 + dx + 1 by class (places, classes)
    y_all, x_all = ys[p_y, p_x], xs[p_y, p_x]
    offset = np.stack(
        [
            (owners[c][0][y_all, x_all] - at[0] + 1) * 3
            + owners[c][1][y_all, x_all]
            - at[1]
            + 1
            for c in range(len(owners))
        ],
        1,
    )
    taken = dict.fromkeys(by_piece, 0)
    out, rows = [], []
    for union, parts in packed({k: len(v) for k, v in by_piece.items()}, most):
        offsets = [b for b in range(9) if union >> b & 1]
        where = np.full(9, -1, np.int64)
        where[offsets] = np.arange(len(offsets))
        places = np.full(TILE, SKIP, np.int64)
        block = np.zeros((len(offsets), TILE, w.shape[-1]), np.float32)
        r = 0
        for piece, n in parts:
            at_places = by_piece[piece][taken[piece] : taken[piece] + n]
            r_of = np.arange(r, r + len(at_places))
            places[r_of] = side * p_y[at_places] + p_x[at_places]
            y, x = y_all[at_places], x_all[at_places]
            for c in range(len(owners)):
                b = offset[at_places, c]
                sel = (piece >> b & 1).astype(bool)
                block[where[b[sel]], r_of[sel]] += w[y[sel], x[sel], c]
            r += len(at_places)
            taken[piece] += n
        rows.append(([(b // 3 - 1, b % 3 - 1) for b in offsets], len(out), places))
        out.extend(block)
    return np.array(out).reshape(-1, TILE, w.shape[-1]), rows


def table_page(rows, first, across, at, form):
    """A tile's table: the row blocks' count, then a block's ENTRY_WORDS: operands,
    first W page, the operands' tile indices (2 x 16 bits a word), places (16 bits)."""
    page = np.zeros(form["table_words"], np.uint32)
    page[0] = len(rows)
    for i, (offsets, start, places) in enumerate(rows):
        entry = page[1 + ENTRY_WORDS * i : 1 + ENTRY_WORDS * (i + 1)]
        entry[0] = len(offsets)
        entry[1] = first + start
        index = [(at[0] + dy) * across + at[1] + dx for dy, dx in offsets]
        index += [0] * (4 - len(index))
        entry[2] = index[0] | index[1] << 16
        entry[3] = index[2] | index[3] << 16
        entry[PLACES_AT:] = (places[0::2] | places[1::2] << 16).astype(np.uint32)
    return page
