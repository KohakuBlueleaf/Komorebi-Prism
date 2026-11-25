"""A core's L1 for a capacity: the buffers that grow with tiles, the largest capacity that
fits, and the refusal in numbers before anything is built."""

from prism.core.capacity import TILE_ROWS
from prism.stages.raster import capacity
from prism.stages.raster.model import numbers
from prism_reference.scene.frame import frame_grid

L1_SLOTS_MARGIN = 16 << 10  # the overlay slots beside session.l1_rows'


def l1_tile_bytes(held):
    """A core's L1 buffers that follow the capacity `held` (setup.h): {name: bytes}."""
    heavy, band_items = capacity.heavy_capacity(held)
    sizes = numbers.sizes(held.tiles, held.recount, heavy, band_items)
    return {
        "counters (counts)": sizes["kCountBytes"],
        "histograms (kept_hist)": sizes["kHistBytes"],
        "slots (next_slots)": sizes["kSlotsBytes"],
        "items (item_words)": sizes["kItemsBytes"],
    }


def per_tile(held):
    """l1_tile_bytes' growth a tile at `held`'s heavy tables (from two tile counts)."""
    low, high = (sum(l1_tile_bytes(held._replace(tiles=t)).values()) for t in (32, 64))
    return (high - low) // 32


def largest_fitting(held, fixed, free):
    """The largest capacity in TILE_ROWS below `held`'s whose L1 (`fixed` bytes that do
    not grow with tiles, and l1_tile_bytes) fits the `free` bytes; 0 when none does."""
    most = 0
    for tiles in range(TILE_ROWS, held.tiles, TILE_ROWS):
        if fixed + sum(l1_tile_bytes(held._replace(tiles=tiles)).values()) <= free:
            most = tiles
    return most


class L1Refused(ValueError):
    """A load refused for a core's L1: the frame's size (W, H), the capacity `held`, the
    bytes L1 needs (`used`) and leaves for buffers (`free`), the buffers that grow with
    tiles, and the largest capacity that fits (`fixed`: the bytes that do not grow)."""

    def __init__(self, held, size, used, free, fixed=None):
        width, height = size
        across, down = frame_grid(size)
        rows = ", ".join(f"{n} {b:,} B" for n, b in l1_tile_bytes(held).items())
        most = None if fixed is None else largest_fitting(held, fixed, free)
        needs = "needs" if fixed is not None else "needs at least"
        fits = f" The largest capacity that fits: {most} tiles." if most else ""
        super().__init__(
            f"a frame of {width} x {height} pixels is {across} x {down} = "
            f"{across * down} tiles (capacity {held.tiles}): a core's L1 {needs} "
            f"{used:,} B of {free:,} B. The buffers that grow with tiles (about "
            f"{per_tile(held)} B a tile): {rows}.{fits}"
        )
        self.used, self.free, self.most = used, free, most


def fits_l1(session, program):
    """Whether `program`'s L1 (session.l1_rows and L1_SLOTS_MARGIN) fits a core."""
    rows = session.l1_rows(program)
    return sum(size for _, size in rows) + L1_SLOTS_MARGIN <= session.l1()[1]


def l1_check(held, size, free):
    """L1Refused when the buffers that grow with tiles alone (with recount, their
    least) take more than the `free` bytes a core's L1 leaves for buffers."""
    least = held._replace(recount=True)
    grows = sum(l1_tile_bytes(least).values())
    if grows > free:
        raise L1Refused(least, size, grows, free)
