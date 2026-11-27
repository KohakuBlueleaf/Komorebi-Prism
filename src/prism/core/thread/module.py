"""What a stage gives the frame's threads: a step of the tile thread as a module (its
planes, list passes, page requests, kept state, code), a thread kind beside the tile
thread, and the pipeline's tile thread composed from steps."""

from dataclasses import dataclass, field

MOVERS = ("mover_a", "mover_b")
COMPUTE = ("unpack", "math", "pack")
PUSHERS = (*MOVERS, *COMPUTE)


@dataclass(frozen=True)
class Plane:
    """A plane of a tile kept in a core's memory while its thread runs: its name (a
    slot's), its format, its tiles."""

    name: str
    format: str
    tiles: int = 1


@dataclass(frozen=True)
class ListPass:
    """One pass of a step over the tile's lists: the layers in the order it walks them
    (a function of the frame's layers giving their indices), streamed to the compute
    CPUs after the passes of the steps before; a list's record bytes and the records a
    list page holds (the loop takes the lists' geometry from here, not from a stage)."""

    layers: object
    block_records: int = 16
    record_bytes: int = 128
    page_records: int = 16


@dataclass(frozen=True)
class Output:
    """A stream of blocks a step pushes for the data-movement CPUs to write: its name,
    a block's bytes, the blocks each half holds, and the function a data-movement CPU
    runs on a block before writing it (None: written as it is):
    `uint32_t f(MoverContext&, payload, bytes)` converts the payload in place and gives
    the bytes to write. A block starts with the loop's 16-byte header (page, offset,
    bytes, page bytes), counted in its bytes."""

    name: str
    block_bytes: int
    blocks: int = 2
    convert: str | None = None


def ring_checked(where, spec, unpushed=False):
    """A ring's (pages, page bytes, pusher[, format]) refused at `where` for a pusher
    not of PUSHERS (or None when `unpushed`: memory, no ring) or a format whose tile is
    not the page."""
    if len(spec) not in (3, 4):
        raise ValueError(f"{where}: (pages, page bytes, pusher[, format]), not {spec}")
    pusher = spec[2]
    if pusher not in PUSHERS and not (unpushed and pusher is None):
        raise ValueError(f"{where} pushed by {pusher!r}, none of {PUSHERS}")
    if len(spec) == 4 and int(spec[1]) != spec[3].tile_bytes:
        raise ValueError(
            f"{where}: pages of {spec[1]} bytes, a {spec[3].dtype} tile is "
            f"{spec[3].tile_bytes}"
        )


@dataclass(frozen=True)
class Step:
    """A step of the tile thread. `header` (from src/prism/) gives
    `<name>_compute(ctx, tile, planes)` for the three compute CPUs, which split the work
    among themselves. `passes`: its list passes; `requests`: the page kinds it may
    request; `outputs`: the streams it pushes; `reads`, `leaves`: its planes; `keeps`:
    state kept on a core across threads ({name: bytes of the capacity held});
    `buffers`: rings of its own ({name: (pages, page bytes, the CPU that pushes)}, or
    with a fourth, a Komorebi format: a page a tile of it; else raw words); `words`: its words of the frame's page, filled by `<name>_frame_words` of `thread`
    (a C file from src/prism/); `codes`: its variants by code (0 the resident one);
    `colour`, `depth`: whether a COLOUR and a DEPTH view's tile thread runs it;
    `begin`: whether the header gives `<name>_begin(ctx)`, run once a command on the
    data-movement CPU that takes the command first, before its first thread. A keep's
    bytes: an int or a function of the capacity held. `fields`: the common fields
    (prism.core.fields) its code uses. `streams`: the rings of `buffers` Komorebi's
    movers move (a stream's halves: among a core's first 32 buffers)."""

    name: str
    header: str
    passes: tuple = ()
    requests: tuple = ()
    outputs: tuple = ()
    reads: tuple = ()
    leaves: tuple = ()
    keeps: dict = field(default_factory=dict)
    buffers: dict = field(default_factory=dict)
    words: tuple = ()
    thread: str | None = None
    codes: dict = field(default_factory=dict)
    colour: bool = True
    depth: bool = False
    begin: bool = False
    fields: tuple = ()
    streams: tuple = ()


@dataclass(frozen=True)
class Kind:
    """A kind of thread beside the tile thread (count, place): the pull it runs in
    (answer.h TP_*), its header (from src/prism/) giving `<name>_movers(ctx, range)`
    for both data-movement CPUs and `<name>_compute(ctx, range)` for the compute CPUs,
    `<name>_end(ctx)` on each when the pull ends; its rings and kept state as a Step's.
    """

    name: str
    pull: int
    header: str
    keeps: dict = field(default_factory=dict)
    buffers: dict = field(default_factory=dict)
    fields: tuple = ()
    streams: tuple = ()


@dataclass(frozen=True)
class TileThread:
    """A pipeline's tile thread: its steps in order and its planes."""

    steps: tuple
    planes: tuple

    def check(self):
        """Refuses steps whose planes do not connect, a plane or a step named twice,
        a ring pushed by no CPU of a core."""
        names = [plane.name for plane in self.planes]
        if len(set(names)) != len(names):
            raise ValueError(f"tile thread: a plane declared twice ({names})")
        steps = [step.name for step in self.steps]
        if len(set(steps)) != len(steps):
            raise ValueError(f"tile thread: a step given twice ({steps})")
        left = set()
        for step in self.steps:
            for name in (*step.reads, *step.leaves):
                if name not in names:
                    raise ValueError(
                        f"tile thread: step {step.name!r} names plane {name!r}, not "
                        f"one of {names}"
                    )
            for name in step.reads:
                if name not in left and name not in step.leaves:
                    raise ValueError(
                        f"tile thread: step {step.name!r} reads plane {name!r}, which "
                        f"no step before it leaves"
                    )
            left |= set(step.leaves)
            for ring, spec in step.buffers.items():
                ring_checked(f"tile thread: step {step.name!r}'s ring {ring!r}", spec)

    def words(self, first, most):
        """{PRISM_TF_<STEP>_<WORD>: its word of the frame's page}: the steps' words in
        the steps' order from word `first` (frame.h TF_STEP_AT); ValueError past word
        `most` (TF_WORDS). The one assignment the kernels and the thread both take."""
        out, word = {}, first
        for step in self.steps:
            for name in step.words:
                out[f"PRISM_TF_{step.name.upper()}_{name.upper()}"] = word
                word += 1
        if word > most:
            raise ValueError(
                f"tile thread: the steps' words end at word {word}, past the page's "
                f"{most}"
            )
        return out

    def passes(self):
        """(step, pass) of every list pass, in the order the stream carries them."""
        return [(step, one) for step in self.steps for one in step.passes]

    def colour(self):
        """The steps a COLOUR view's tile thread runs."""
        return tuple(step for step in self.steps if step.colour)

    def depth(self):
        """The steps a DEPTH view's tile thread runs."""
        return tuple(step for step in self.steps if step.depth)
