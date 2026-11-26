"""The handler `work`'s host side: the tile thread and the kinds a pipeline's options
name, composed for the frame's layers, and the class made; a tile thread's record and
the frame's page as record.h and frame.h lay them out."""

import numpy as np

from prism.core.capacity import default_capacity
from prism.core.implementation import Host
from prism.program.dispatch import thread as dispatch
from prism.program.frame import device, generate
from prism_common.build import located

TF, TR, TA = generate.TF, generate.TR, generate.TA
WHOLE_ROWS = 32  # a whole tile's end row
# the options naming the composition: the tile thread (a dotted path to a TileThread),
# the kinds (dotted paths to Kinds), the frame's layers (names, in order)
THREAD, KINDS, LAYERS = "frame_thread", "frame_kinds", "frame_layers"
DISPATCH, DEFINES = "frame_dispatch", "frame_defines"
LAYER_WORDS = (
    "mesh",
    "range_first",
    "blocks",
    "shade",
    "lists",
    "counts",
    "rows",
    "positions",
)


def record(tile, first_row=0, end_row=WHOLE_ROWS, page=0, layers=()):
    """A tile thread's record (record.h): `layers` a (first slot, entries) a layer
    (entries 0: none of it); its weight their entries, its layers their bits."""
    if len(layers) > TR["TR_LAYERS"]:
        raise ValueError(
            f"record: {len(layers)} layers, a record holds {TR['TR_LAYERS']}"
        )
    if not 0 <= first_row < end_row <= WHOLE_ROWS or not 0 <= tile <= 0xFFFF:
        raise ValueError(f"record: tile {tile}, rows {first_row} to {end_row}")
    words = np.zeros(TR["TR_WORDS"], np.uint32)
    words[0] = tile | first_row << 16 | end_row << 24
    words[1] = sum(entries for _, entries in layers)
    words[2] = sum(1 << layer for layer, (_, n) in enumerate(layers) if n)
    words[3] = page
    for layer, (slot, entries) in enumerate(layers):
        words[4 + 2 * layer] = slot
        words[5 + 2 * layer] = entries
    return words


def record_fields(words):
    """A record's words as a dict of record()'s arguments and its weight and bits."""
    words = np.asarray(words, np.uint32)
    word0 = int(words[0])
    return {
        "tile": word0 & 0xFFFF,
        "first_row": word0 >> 16 & 0xFF,
        "end_row": word0 >> 24,
        "weight": int(words[1]),
        "bits": int(words[2]),
        "page": int(words[3]),
        "layers": [
            (int(words[4 + 2 * n]), int(words[5 + 2 * n]))
            for n in range(TR["TR_LAYERS"])
        ],
    }


def frame_page(numbers, layers=(), words=None):
    """The frame's page (TF_WORDS words): `numbers` {name: value} of frame.h's TF_*
    (lower case, without TF_; view and kind given apart as view, kind), `layers` a dict
    a layer of LAYER_WORDS, `words` {word: value} of the steps' (Composition.words)."""
    if len(layers) > TR["TR_LAYERS"]:
        raise ValueError(
            f"frame page: {len(layers)} layers, it holds {TR['TR_LAYERS']}"
        )
    page = np.zeros(TF["TF_WORDS"], np.uint32)
    numbers = dict(numbers)
    page[TF["TF_VIEW"]] = numbers.pop("view", 0) | numbers.pop("kind", 0) << 8
    for name, value in numbers.items():
        key = f"TF_{name.upper()}"
        if key not in TF or key in ("TF_LAYER_AT", "TF_LAYER_WORDS", "TF_WORDS"):
            raise ValueError(f"frame page: no word {name!r}")
        page[TF[key]] = value
    page[TF["TF_LAYER_COUNT"]] = len(layers)
    for index, given in enumerate(layers):
        unknown = set(given) - set(LAYER_WORDS)
        if unknown:
            raise ValueError(f"frame page: layer words {', '.join(sorted(unknown))}")
        at = TF["TF_LAYER_AT"] + index * TF["TF_LAYER_WORDS"]
        for name, value in given.items():
            page[at + TF[f"TF_L_{name.upper()}"]] = value
    for name, value in (words or {}).items():
        page[int(name)] = value
    return page


class FrameHost(Host):
    """The handler `work` on `session`: its composition from the options' tile thread,
    kinds and layers at the options' capacity (`capacity`, else the default frame's);
    the dispatcher's capacity and the steps' and kinds' define functions by option."""

    def __init__(self, session, scene, options):
        self.session = session
        self.scene = scene
        self.options = dict(options)
        self.held = self.options.get("capacity") or default_capacity()
        self.composition = None

    def prepare(self):
        """The tile thread and kinds resolved once and composed."""
        if THREAD not in self.options:
            raise ValueError(
                f"frame program: the option {THREAD!r} names no tile thread"
            )
        thread = located(self.options[THREAD])
        kinds = tuple(located(path) for path in self.options.get(KINDS, ()))
        layers = tuple(self.options.get(LAYERS, ("opaque",)))
        self.composition = generate.compose(thread, kinds, layers, self.held)

    def defines(self):
        """The kernels' build defines beside the steps' words: the dispatcher's
        capacity's (one source with the thread), then each named function's of the
        capacity held."""
        if DISPATCH not in self.options:
            raise ValueError(
                f"frame program: the option {DISPATCH!r} gives no dispatcher capacity"
            )
        out = dict(dispatch.defines(self.options[DISPATCH]))
        for path in self.options.get(DEFINES, ()):
            out |= located(path)(self.held)
        return out

    def word_defines(self):
        """{PRISM_TF_<STEP>_<WORD>: word} for the frame's thread's C."""
        return dict(self.composition.words)


def made(host):
    """The class of the handler `work` made for a prepared FrameHost."""
    return device.made(host, host.composition, host.defines())
