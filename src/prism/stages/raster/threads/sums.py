"""The sums as an ordinary command of a class of their own: every core of the view's
group takes the slices of its rank, the frame's page as the command's block."""

import komorebi as km

from prism.core.compute import FRAME_COMPUTE
from prism.stages.raster import capacity
from prism.stages.raster.threads import layout

SUMS = km.kernel(movement="kernels/sums_movement.hpp", entry="geometry_k::sums")
DEFAULT_WORDS = layout.scratch_bytes() // 4


class RasterSums(km.Program, compute=FRAME_COMPUTE):
    """SUMS on every core of a group, as the frame's thread sends it between the count
    and the place pulls; its sizes those of the capacity it is made for (made)."""

    SCRATCH_WORDS = km.constant(DEFAULT_WORDS)  # a mover's SumScratch, whole lines
    scratch_a: km.L1[km.u32, 1, SCRATCH_WORDS] = km.own(push=None, raw=True)
    scratch_b: km.L1[km.u32, 1, SCRATCH_WORDS] = km.own(push=None, raw=True)

    @km.handler(SUMS)
    def sums(self):
        """For each slice of this core's rank: the totals, the cut tiles' bands, the
        records in order of weight, the slice's words, every core's positions."""


def made(held, slices, slice_records=layout.SLICE_RECORDS, session=None):
    """The class made for a capacity `held` of `slices` slices of `slice_records`
    records."""
    return RasterSums(
        SCRATCH_WORDS=layout.scratch_bytes(slice_records) // 4,
        defines=capacity.capacity_defines(held) | layout.defines(slices, slice_records),
        session=session,
        depth=1,
    )
