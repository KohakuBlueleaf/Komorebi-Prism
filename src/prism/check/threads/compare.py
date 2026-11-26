"""Comparisons of what the card left against the model or another picture: arrays word
by word with the first difference, the lists item by item (the same entries, and in
the model's order), two pictures byte for byte with the first differing tile."""

import numpy as np

from prism.program.frame.host import record_fields
from prism.stages.raster.model.numbers import K
from prism.stages.raster.model.threads import M, R
from prism_reference.scene.frame import TILE

SHOWN = 8  # differences listed at most in a comparison


def exact(name, got, want):
    """`got` against `want` word for word: {name, equal, differ, first} (first: the
    index and both values of the first difference)."""
    got, want = np.asarray(got), np.asarray(want)
    if got.shape != want.shape:
        return {
            "name": name,
            "equal": False,
            "shape": [list(got.shape), list(want.shape)],
        }
    wrong = np.argwhere(got != want)
    out = {"name": name, "equal": not len(wrong), "differ": len(wrong)}
    if len(wrong):
        at = tuple(int(n) for n in wrong[0])
        out["first"] = {"at": list(at), "card": int(got[at]), "model": int(want[at])}
    return out


def records(got, want, slice_records):
    """The records tensor against the model's records: exact, and the first
    differing record decoded on both sides with its slice and place."""
    out = exact("records", got, want)
    rows = np.flatnonzero((np.asarray(got) != np.asarray(want)).any(axis=1))
    if out["equal"] or not len(rows):
        return out
    row = int(rows[0])
    out["first_record"] = {
        "number": row,
        "slice": row // slice_records,
        "place": row % slice_records,
        "card": record_fields(got[row]),
        "model": record_fields(want[row]),
    }
    out["records_differ"] = len(rows)
    return out


def item_spans(laid, layer):
    """(record number, tile, first row, end row, first slot, entries) of each record
    of the model's slices for `layer`: its list's slots in the layer's lists."""
    count = laid["slice_records"]
    words, held = laid["slice_words"], laid["records"]
    out = []
    for s in range(len(words)):
        place = int(words[s, M["TS_PLACE"](layer)])
        for n in range(int(words[s, R["TS_RECORDS"]])):
            row = held[s * count + n]
            fields = record_fields(row)
            first = place + int(row[M["TR_LAYER_SLOT"](layer)])
            entries = int(row[M["TR_LAYER_ENTRIES"](layer)])
            out.append(
                (
                    s * count + n,
                    fields["tile"],
                    fields["first_row"],
                    fields["end_row"],
                    first,
                    entries,
                )
            )
    return out


def sorted_rows(rows):
    """Rows of words in lexicographic order (a multiset's form)."""
    if not len(rows):
        return rows
    return rows[np.lexsort(rows.T[::-1])]


def triangles(slots):
    """The triangle numbers of list slots (kRecTri, a float), as a set of ints."""
    column = np.ascontiguousarray(slots[:, K["kRecTri"]]).view(np.float32)
    return set(column.astype(np.int64).tolist())


def lists(laid, layer, got):
    """A layer's lists read back (slots, 32 words) against the model's, item by item:
    the same entries (the judgement) and in the model's order (reported); the first
    item that differs with the records' indices missing and extra."""
    want = laid["lists"][layer]["slots"]
    spans = item_spans(laid, layer)
    total = len(want)
    out = {"name": f"lists.{layer}", "items": len(spans), "slots": total}
    if len(got) < total:
        return out | {"equal": False, "short": [len(got), total]}
    unlike, unordered, first = 0, 0, None
    for number, tile, first_row, end_row, slot, entries in spans:
        mine, theirs = got[slot : slot + entries], want[slot : slot + entries]
        same = np.array_equal(sorted_rows(mine), sorted_rows(theirs))
        unordered += same and not np.array_equal(mine, theirs)
        if same:
            continue
        unlike += 1
        if first is None:
            have, wanted = triangles(mine), triangles(theirs)
            first = {
                "record": number,
                "tile": tile,
                "rows": [first_row, end_row],
                "slots": [slot, slot + entries],
                "missing": sorted(wanted - have)[:SHOWN],
                "extra": sorted(have - wanted)[:SHOWN],
                "words_differ": sorted(
                    set(
                        np.flatnonzero(
                            (sorted_rows(mine) != sorted_rows(theirs)).any(0)
                        )
                    )
                )[:SHOWN],
            }
    out |= {"equal": unlike == 0, "items_differ": unlike, "items_reordered": unordered}
    return out | ({"first": first} if first else {})


def tile_of(pixel_row, pixel_column, across):
    """The tile of a pixel."""
    return (pixel_row // TILE) * across + pixel_column // TILE


def pictures(got, want):
    """Two pictures (H, W, 4) uint8 byte for byte: the bytes and pixels that differ,
    the largest difference, the tiles that differ and the first of them."""
    got, want = np.asarray(got), np.asarray(want)
    if got.shape != want.shape:
        return {"equal": False, "shape": [list(got.shape), list(want.shape)]}
    gap = np.abs(got.astype(np.int16) - want.astype(np.int16))
    pixels = gap.any(axis=2)
    out = {
        "equal": not pixels.any(),
        "bytes_differ": int(np.count_nonzero(gap)),
        "pixels_differ": int(pixels.sum()),
        "largest": int(gap.max(initial=0)),
    }
    if out["equal"]:
        return out
    across = -(-got.shape[1] // TILE)
    rows, columns = np.nonzero(pixels)
    tiles = tile_of(rows, columns, across)
    out["tiles_differ"] = len(np.unique(tiles))
    first = int(tiles.min())
    inside = tiles == first
    out["first_tile"] = {
        "tile": first,
        "at": [first % across, first // across],
        "pixels": int(inside.sum()),
        "rows": [int(rows[inside].min() % TILE), int(rows[inside].max() % TILE) + 1],
    }
    return out


def records_of_tile(held, tile, rows, slice_of, slice_records, counts=None):
    """The records of `tile` whose rows reach `rows` (first, end) among the records
    tensor's words `held`, in its slice `slice_of` (counts: each slice's TS_RECORDS
    when read): [(number, its fields)]."""
    first = slice_of * slice_records
    end = first + (slice_records if counts is None else int(counts[slice_of]))
    out = []
    for number in range(first, min(end, len(held))):
        fields = record_fields(held[number])
        reach = fields["first_row"] < rows[1] and fields["end_row"] > rows[0]
        if fields["tile"] == tile and reach:
            out.append((number, fields))
    return out
