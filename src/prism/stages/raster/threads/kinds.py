"""The geometry thread's kinds beside the tile thread: count and place, each with the
rings its range moves through (the pass's own spaces among them; the block pairs its
streams), and the state it keeps on a core during its pull."""

from prism.core.headers import INCLUDE, defined
from prism.core.thread.module import Kind
from prism.stages.raster.model.numbers import TILES, S
from prism.stages.raster.threads import layout

ANSWER = defined(INCLUDE / "thread" / "answer.h")
COUNT_HEADER = "stages/raster/threads/kernels/count.hpp"
PLACE_HEADER = "stages/raster/threads/kernels/place.hpp"
# the mover that streams a range's blocks (0 mover A, 1 mover B: the build define
# PRISM_GEO_STREAMER); the other is the integer side
STREAMER = 0
MOVERS = ("mover_a", "mover_b")


def pair(name, page_bytes, streamer=STREAMER):
    """A ring pair's two halves {name_a, name_b}: the streaming mover's kMeshPages
    pages, the other's one (it moves no block)."""
    return {
        f"{name}_{letter}": (
            S["kMeshPages"] if mover == streamer else 1,
            page_bytes,
            MOVERS[mover],
        )
        for mover, letter in enumerate("ab")
    }


def pass_spaces():
    """The stage-wise pass's own spaces on the pack CPU, a page each (it takes them as
    buffers): its work, its cost knots, its profile words."""
    return {
        "work": (1, S["kWorkBytes"], None),
        "costs": (1, 4 * (S["kCostKnots"] + 1), None),
        "profile": (1, S["kSProfBytes"], None),
    }


def kinds(
    tiles=TILES, slices=None, slice_records=layout.SLICE_RECORDS, streamer=STREAMER
):
    """(count, place) for a capacity of `tiles` tiles and `slices` slices (None: the
    capacity's grid of 32 tiles a row in runs of layout.SLICE_TILES)."""
    if slices is None:
        slices = layout.slices_of(32, -(-tiles // 32))
    blocks = pair("mesh", S["kMeshBytes"], streamer)
    shades = pair("shade", S["kShadeBlockBytes"], streamer)
    out = {"out": (S["kOutPages"], S["kOutBytes"], "pack"), **pass_spaces()}
    count = Kind(
        name="count",
        pull=ANSWER["TP_COUNT"],
        header=COUNT_HEADER,
        keeps={
            "counts": layout.count_bytes(tiles),
            "rows": layout.hist_bytes(tiles),
        },
        buffers={**blocks, **out},
        fields=(),
        streams=tuple(blocks),
    )
    place = Kind(
        name="place",
        pull=ANSWER["TP_PLACE"],
        header=PLACE_HEADER,
        keeps={
            "positions": layout.position_bytes(slices, slice_records),
            "places": layout.places_bytes(slices),
        },
        buffers={
            **blocks,
            **shades,
            **out,
        },
        fields=(),
        streams=(*blocks, *shades),
    )
    return count, place


COUNT, PLACE = kinds()
