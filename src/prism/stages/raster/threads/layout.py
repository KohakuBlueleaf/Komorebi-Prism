"""The geometry thread's sizes that follow a capacity: a core's counts, row histograms and
positions pages of a layer, the slices' places, the sums' scratch, a view's slices."""

from pathlib import Path

from prism.core.headers import INCLUDE, constexpr, defined

KERNELS = Path(__file__).resolve().parent / "kernels"
G = constexpr(KERNELS / "geometry.h")
RECORD = defined(INCLUDE / "thread" / "record.h")
LAYERS = RECORD["TR_LAYERS"]
RECORD_BYTES = G["kRecordBytes"]
SLICE_BYTES = G["kSliceBytes"]
LINE = G["kLine"]
# first-form sizes of a view's slices: the tiles a slice holds, the records it holds
SLICE_TILES = 16
SLICE_RECORDS = 32


def line_up(size):
    """`size` bytes up to whole DRAM lines."""
    return -(-size // LINE) * LINE


def slices_of(across, down, slice_tiles=SLICE_TILES):
    """The slices of a grid of `across` x `down` tiles: runs of `slice_tiles` along a
    row, ceil(across / slice_tiles) a row."""
    if not 0 < slice_tiles <= G["kSliceTilesMost"]:
        raise ValueError(
            f"a slice of {slice_tiles} tiles: between 1 and {G['kSliceTilesMost']} "
            f"(kernels/geometry.h kSliceTilesMost)"
        )
    return -(-across // slice_tiles) * down


def count_bytes(tiles):
    """A core's counts page of a layer: a word a tile of the capacity's `tiles`."""
    return G["kCountTileBytes"] * tiles


def hist_bytes(tiles):
    """A core's row histograms page of a layer: 64 bytes a tile."""
    return G["kHistTileBytes"] * tiles


def position_bytes(slices, slice_records=SLICE_RECORDS):
    """A core's positions page of a layer: a slice's tile words, then its band
    entries, for `slices` slices of `slice_records` records."""
    tile_words = G["kSliceTilesMost"] * slices
    return 4 * (tile_words + G["kBandWords"] * slice_records * slices)


def places_bytes(slices):
    """The slices' words a core reads at a layer's first range: a line a slice."""
    return SLICE_BYTES * slices


def scratch_bytes(slice_records=SLICE_RECORDS):
    """A mover's scratch of the sums (kernels/sums/reads.hpp SumScratch), whole lines:
    the slice's tables and items, then the reads' and writes' line-aligned images."""
    most, cores, groups = G["kSliceTilesMost"], G["kSumCores"], G["kGroups"]
    item_words = 5 + 2 * LAYERS
    tables = 4 * (LAYERS * most + 3 * most + 2 * LAYERS * groups)
    tables += 4 * (2 * slice_records + LAYERS) + 4 * item_words * slice_records
    images = cores * 4 * LINE  # counts' runs
    images += cores * LAYERS * G["kHistTileBytes"]
    images += cores * 4 * most
    images += line_up(cores * 4 * G["kBandWords"] * slice_records)
    images += RECORD_BYTES * slice_records + SLICE_BYTES
    return line_up(tables) + images


def layer_pages(tiles, slices, slice_records=SLICE_RECORDS):
    """{tensor: page bytes} of the per-layer tensors the geometry thread and the sums
    use, a page a core: counts, rows (TF_L_COUNTS, TF_L_ROWS), positions."""
    return {
        "counts": count_bytes(tiles),
        "rows": hist_bytes(tiles),
        "positions": position_bytes(slices, slice_records),
    }


def view_bytes(slices, slice_records=SLICE_RECORDS):
    """{what: bytes} of a view's tables: the records (TF_RECORDS, a tensor of 64-byte
    pages) and the slices' words (TF_SLICES, in the regions' bank)."""
    return {
        "records": RECORD_BYTES * slices * slice_records,
        "slices": SLICE_BYTES * slices,
    }


def defines(slices, slice_records=SLICE_RECORDS):
    """The build defines the kinds and the sums need beside the capacity's."""
    return {"RASTER_SLICES": str(slices), "TR_SLICE_RECORDS": str(slice_records)}
