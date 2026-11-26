"""The frame's thread as Komorebi's pulls: its unit in the thread's layout (regions,
numbers, columns, times, results, build numbers), the numbers and a layer's columns a
host writes, the steps' words, and the thread declared with its C and generated part."""

from dataclasses import dataclass
from pathlib import Path

from komorebi.program import thread as km_thread

from prism.core.headers import INCLUDE, defined
from prism.core.unit import Region, Unit
from prism.program.director import thread as director
from prism.program.dispatch import generate
from prism.program.jobs import frame as jobs
from prism.stages.raster.threads import layout as geometry
from prism_common.paths import build_root

RUNTIME = Path(__file__).resolve().parent / "c"
SOURCES = ("dispatch_choose.c", "dispatch_view.c")
SRC = Path(__file__).resolve().parents[3]  # src/: a step's `thread` is from src/prism/
FRAME = defined(INCLUDE / "thread" / "frame.h")
RECORD = defined(INCLUDE / "thread" / "record.h")
CHOOSE = defined(RUNTIME / "dispatch_choose.h")
PORTS_CORES = km_thread.layout()["KMX_PORTS_CORES"]
STEP_AT = (
    FRAME["TF_LAYER_AT"] + RECORD["TR_LAYERS"] * FRAME["TF_LAYER_WORDS"]
)  # TF_STEP_AT
POLICIES = {
    name.removeprefix("DP_POLICY_").lower(): value
    for name, value in CHOOSE.items()
    if name.startswith("DP_POLICY_") and name != "DP_POLICIES"
}
P = generate.PREFIX
NUMBERS = tuple(
    P + name
    for name in (
        "policy",
        "near",
        "heavy",
        "range_blocks",
        "records",
        "display",
    )
)
COLUMNS = tuple(
    P + name
    for name in (
        "mesh",
        "blocks",
        "shade",
        "lists",
        "list_slots",
        "counts",
        "rows",
        "positions",
    )
)
PHASES = P + "phases"  # a view's phases (dispatch.h DP_PHASE_*; 0: every phase)
TIMES = tuple(
    P + name for name in ("count", "sums", "running", "place", "words", "tile")
)
# the ranges, the tile threads, those given near; the cores an update wanted when a
# view was refused for them (DP_NO_CORES)
RESULTS = tuple(P + name for name in ("ranges", "tile_threads", "near_given", "wanted"))


@dataclass(frozen=True)
class Capacity:
    """What the dispatcher's regions hold: the count ranges of a view, the slices of a
    view, the records a slice holds, the tiles a slice holds (the geometry's layout's).
    """

    ranges: int
    slices: int
    slice_records: int = geometry.SLICE_RECORDS
    slice_tiles: int = geometry.SLICE_TILES


def capacity_of(ranges, across, down):
    """The capacity of `ranges` count ranges on a grid of `across` x `down` tiles at
    most: its slices by the geometry's layout."""
    return Capacity(ranges, geometry.slices_of(across, down))


def page_bytes(capacity):
    """The frame's page: the block of a view's commands."""
    return 4 * FRAME["TF_WORDS"]


def slices_bytes(capacity):
    """The slices' words: TS_WORDS a slice."""
    return 4 * RECORD["TS_WORDS"] * capacity.slices


def log_bytes(capacity):
    """The count pull's log: a count a port's core, then its ranges (KMX_PULL_LOG_BYTES
    of the ranges a view)."""
    return 4 * PORTS_CORES * (1 + capacity.ranges)


def state_bytes(capacity):
    """The choice's state (dp_choose_t): its head, a core's words, a slice's words."""
    words = CHOOSE["DP_CHOOSE_HEAD_WORDS"] + CHOOSE["DP_CORE_WORDS"] * PORTS_CORES
    return 4 * (words + CHOOSE["DP_SLICE_WORDS"] * capacity.slices)


def defines(capacity):
    """The dispatcher's build numbers for `capacity`: the geometry's (RASTER_SLICES,
    TR_SLICE_RECORDS), the ranges, the slices and the tiles a slice."""
    return geometry.defines(capacity.slices, capacity.slice_records) | {
        "DP_RANGES_MOST": f"{capacity.ranges}u",
        "DP_SLICES_MOST": f"{capacity.slices}u",
        "DP_SLICE_TILES": f"{capacity.slice_tiles}u",
    }


UNIT = Unit(
    regions={
        P + "page": Region(page_bytes),
        P + "slices": Region(slices_bytes),
        P + "log": Region(log_bytes),
        P + "state": Region(state_bytes),
    },
    numbers=(*NUMBERS, PHASES),
    columns=COLUMNS,
    times=TIMES,
    results=RESULTS,
    defines=defines,
)


def entry(capacity):
    """The dispatcher as the layout takes a unit: (name, Unit, host)."""
    sizes = (capacity.ranges, capacity.slices, capacity.slice_records)
    if min(*sizes, capacity.slice_tiles) <= 0:
        raise ValueError(f"dispatch: an empty capacity ({capacity})")
    return generate.NAME, UNIT, capacity


def numbers(policy, near, heavy, range_blocks, records, display):
    """{number: value} of the loaded run's numbers: the policy by name, the near
    distance in slices, the weight above which a tile is cut, the blocks a count range,
    the records' and the display's addresses."""
    if policy not in POLICIES:
        raise ValueError(f"dispatch: policy {policy!r}, not one of {sorted(POLICIES)}")
    if range_blocks <= 0 or near < 0:
        raise ValueError(f"dispatch: {range_blocks} blocks a range, near {near}")
    values = (POLICIES[policy], near, heavy, range_blocks, records, display)
    return dict(zip(NUMBERS, (int(value) for value in values), strict=True))


def columns(mesh, blocks, shade, lists, list_slots, counts, rows, positions):
    """{column: value} of a (view, layer)'s row: its triangle blocks' address and
    count, its shade blocks' address (0: not shaded), its lists' address and slots, its
    counts', row histograms' and positions' addresses."""
    values = (mesh, blocks, shade, lists, list_slots, counts, rows, positions)
    return dict(zip(COLUMNS, (int(value) for value in values), strict=True))


def frame_words(tile_thread):
    """[(the C file, its function, depth)] of each step with words, in the steps'
    order; ValueError for a step with words and no thread file."""
    out = []
    for step in tile_thread.steps:
        if not step.words:
            continue
        if step.thread is None:
            raise ValueError(f"dispatch: step {step.name!r} has words and no thread")
        path = (SRC / "prism" / step.thread).resolve()
        out.append((path, f"{step.name}_frame_words", step.depth))
    return out


def builder(builders, owner, handler):
    """The C builder of `handler` of the class of implementation `owner`."""
    if owner not in builders:
        raise ValueError(
            f"dispatch: no class of {owner!r} among {sorted(builders)} gives {handler}"
        )
    return f"{builders[owner]}_{handler}"


def declare(assembled, layout, tile_thread, work_owner, sums_owner):
    """program.thread(...) for `layout` (holding the entry): the dispatcher's C, the
    units' C (the job thread's frame unit's too), `tile_thread`'s frame words, the
    builders of `work` (class of `work_owner`) and `sums` (of `sums_owner`)."""
    program = assembled.program
    owners = {owner for owner, _, _ in layout.units}
    with_unit = [i for i in assembled.pipeline.implementations if i.name in owners]
    sources, includes = [], []
    for implementation in with_unit:
        unit_sources, unit_includes = director.unit_files(implementation)
        sources += unit_sources
        includes += unit_includes
    if jobs.OWNER in owners:
        sources += [jobs.FOLDER / source for source in jobs.FRAME_UNIT.sources]
        includes += [jobs.FOLDER / include for include in jobs.FRAME_UNIT.includes]
    words = frame_words(tile_thread)
    for path, _, _ in words:
        if path not in sources:
            sources.append(path)
        includes.append(path.parent)
    own = [RUNTIME / source for source in SOURCES]
    stems = [source.stem for source in [*own, *sources]]
    if len(set(stems)) != len(stems):
        raise ValueError(f"thread sources with one name: {', '.join(sorted(stems))}")
    builders = director.builders(assembled)
    built = {
        "work": builder(builders, work_owner, "work"),
        "sums": builder(builders, sums_owner, "sums"),
    }
    name = director.program_name(program)
    generated = generate.write(
        layout,
        f"{name}_thread.h",
        name.upper(),
        builders,
        built,
        tile_thread.words(STEP_AT, FRAME["TF_WORDS"]),
        tuple((function, depth) for _, function, depth in words),
        build_root() / "thread" / name,
    )
    return program.thread(
        cluster=layout.cluster,
        sources=[director.RUNTIME / "director.c", generated / generate.SOURCE, *own]
        + sources,
        includes=[director.RUNTIME, RUNTIME, generated, INCLUDE]
        + list(dict.fromkeys(includes)),
        regions=layout.region_values(),
        handlers=layout.handlers(),
        defines=layout.defines,
        deadline=director.DEADLINE,
    )
