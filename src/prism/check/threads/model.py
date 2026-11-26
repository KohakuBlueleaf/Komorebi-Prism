"""The model's layout of a view for the card (stages/raster/model/threads.py over the
frame's layers as the card holds them), its tensors' images page by page, and the
count pull's log read back as the core of each range."""

import numpy as np
from komorebi.program import thread as km_thread

from prism.check.threads.layers import card_records
from prism.stages.raster.model import threads
from prism.stages.raster.model.numbers import GROUPS
from prism_reference.raster.setup import grid

PORTS_CORES = km_thread.layout()["KMX_PORTS_CORES"]
NO_CORE = -1


def view_of(scene):
    """The model's view of a COLOUR view of `scene`: its camera and size, its tiles'
    pages the display's (first 0, a row of the grid a row)."""
    across, _ = grid(scene)
    return {
        "camera": scene["camera"],
        "size": tuple(scene["size"]),
        "page_first": 0,
        "page_across": across,
    }


def laid_out(
    layers, view, capacity, heavy, range_blocks, log=None, cores=None, wide=False
):
    """The model's layout of `layers` ([(name, flat scene, shade rows or None)]) for
    the dispatcher's `capacity`, each layer's list slots the card's records (`log`:
    the core of each range, None one core; `wide`: a wide build's box columns)."""
    laid = threads.layout(
        [(name, one) for name, one, _ in layers],
        view,
        log,
        slice_tiles=capacity.slice_tiles,
        heavy=heavy or None,
        range_blocks=range_blocks,
        cores=cores,
        slice_records=capacity.slice_records,
        held=capacity.slices,
    )
    for layer, (name, one, shade) in enumerate(layers):
        pieces, packed = card_records(one, shade, wide)
        if not np.array_equal(pieces["tri"], laid["pieces"][layer]["tri"]):
            raise ValueError(f"layer {name}: the card's pieces are not the model's")
        written = laid["lists"][layer]["pieces"]
        laid["lists"][layer]["slots"] = packed[np.maximum(written, 0)]
    return laid


def pages(words, page_bytes, count=None):
    """`words` (any shape, 4-byte items) as uint8 rows of `page_bytes`, padded with
    zeros to whole pages (`count`: to that many pages at least)."""
    raw = np.ascontiguousarray(words).view(np.uint8).reshape(-1)
    total = max(-(-len(raw) // page_bytes), count or 0)
    out = np.zeros(total * page_bytes, dtype=np.uint8)
    out[: len(raw)] = raw
    return out.reshape(total, page_bytes)


def words_of(rows):
    """uint8 page rows read back as uint32 words, a row each."""
    return np.ascontiguousarray(rows).view(np.uint32).reshape(len(rows), -1)


def records_image(laid, capacity):
    """The records tensor's words (capacity's slices x records a slice, TR_WORDS)."""
    out = np.zeros(
        (capacity.slices * capacity.slice_records, threads.TR_WORDS), np.uint32
    )
    out[: len(laid["records"])] = laid["records"]
    return out


def slices_image(laid, capacity):
    """The slices' words (capacity's slices, TS_WORDS), the places written."""
    out = np.zeros((capacity.slices, threads.TS_WORDS), np.uint32)
    out[: len(laid["slice_words"])] = laid["slice_words"]
    return out


def counts_image(laid, layer, page_words):
    """Each core's counts page of `layer` (cores, page_words): a word a tile."""
    counts = laid["counts"][layer]
    out = np.zeros((len(counts), page_words), np.uint32)
    out[:, : counts.shape[1]] = counts
    return out


def rows_image(laid, layer, page_words):
    """Each core's row histograms page of `layer` (cores, page_words): a tile's 16
    uint16 starts, then its 16 ends, by 2-row group."""
    starts, ends = laid["starts"][layer], laid["ends"][layer]
    cores, tiles, _ = starts.shape
    halves = np.concatenate([starts, ends], axis=2).astype(np.uint16)
    out = np.zeros((cores, 2 * page_words), np.uint16)
    out[:, : tiles * 2 * GROUPS] = halves.reshape(cores, -1)
    return out.view(np.uint32)


def positions_image(laid, layer, page_words):
    """Each core's positions page of `layer` (cores, page_words)."""
    page = laid["positions_pages"][layer]
    out = np.zeros((len(page), page_words), np.uint32)
    out[:, : page.shape[1]] = page
    return out


def log_cores(raw, ranges):
    """The core of each of `ranges` ranges from the count pull's log (bytes of the
    region): a count a port's core, then its ranges; a port core is its rank.
    (cores of the ranges, the ranks that took any); ValueError on a range taken
    twice or by none."""
    words = np.frombuffer(bytes(raw), dtype=np.uint32)
    held = len(words) // PORTS_CORES - 1
    counts, lists = words[:PORTS_CORES], words[PORTS_CORES:]
    out = np.full(ranges, NO_CORE, dtype=np.int64)
    for core in range(PORTS_CORES):
        for place in range(min(int(counts[core]), held)):
            taken = int(lists[core * held + place])
            if taken >= ranges or out[taken] != NO_CORE:
                raise ValueError(f"log: range {taken} taken twice or past {ranges}")
            out[taken] = core
    if (out == NO_CORE).any():
        raise ValueError(f"log: {int((out == NO_CORE).sum())} ranges taken by none")
    return out, sorted(set(out.tolist()))
