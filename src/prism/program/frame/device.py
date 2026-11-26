"""The handler `work` on every core: a class made for one Composition, its hand kernels
the generated program (one file for both movers and the compute CPUs), its fields the
loop's rings, the outputs' pairs, the steps' and kinds' rings and the common fields (its
memory a part of the command space).
"""

import types

import komorebi as km
from komorebi.dsl.compile.layout import FIRST_UPPER

from prism.core import fields
from prism.core.compute import FRAME_COMPUTE
from prism.program.frame import generate
from prism_common.paths import build_root

ENTRY = "prism_frame::work"  # work_movement on both movers, work_compute on compute
HANDLER = "work"
WORD = 4
STREAM_INDICES = FIRST_UPPER  # a stream's half is among a core's first buffers


def field_of(pages, page_bytes, pusher):
    """A ring's annotation and its km.own (raw words; pusher None: no ring)."""
    if page_bytes % WORD:
        raise ValueError(f"frame program: a ring's pages of {page_bytes} bytes, words")
    return km.L1[km.u32, pages, page_bytes // WORD], km.own(push=pusher, raw=True)


def frame_class(composition, program_file):
    """The class of the handler `work` for the composition and its generated program
    `program_file`: the rings by name, the common fields its steps and kinds name."""
    annotations, owns = {}, {}
    for name, (pages, page_bytes, pusher) in composition.rings.items():
        annotations[name], owns[name] = field_of(pages, page_bytes, pusher)
    common = composition.common()
    annotations |= {name: fields.field(name) for name in common}
    owns |= {name: fields.own(name) for name in common}
    constants = {
        fields.varying(name): fields.CONSTANTS[fields.varying(name)]
        for name in common
        if fields.varying(name) is not None
    }

    def body(namespace):
        """The class body: its annotations, fields, constants and the handler."""
        namespace["__doc__"] = (
            "WORK on every core of a view's pull: each core takes threads from its "
            "X280 core, hands each to its compute CPUs and both movers, and runs it "
            "to its end."
        )
        namespace["__annotations__"] = annotations  # the rings and the common fields
        namespace |= owns | constants
        namespace["work"] = km.handler(
            km.kernel(movement=program_file, compute=program_file, entry=ENTRY)
        )(work)

    return types.new_class("FrameWork", (km.Program,), {"compute": FRAME_COMPUTE}, body)


def work(self):
    """WORK: the threads of the command's pull (the block: the frame's page), each run
    where it was taken."""


def made(host, composition, defines):
    """The class made on the host's session for the composition, its program
    generated under the build folder, with the common fields' sizes at the host's
    capacity and `defines` beside the steps' words."""
    path = generate.write(composition, build_root() / "frame")
    cls = frame_class(composition, path)
    given = {name: str(word) for name, word in composition.words.items()}
    return cls(
        **fields.given(cls, host.held),
        defines=dict(defines)
        | fields.defines(host.held)
        | fields.table_defines(cls, host.held)
        | given,
        session=host.session,
        depth=1,
    )


def streams_checked(program, composition):
    """The made program's index of each stream half of the composition; refused with
    the indices when one is past a core's first STREAM_INDICES buffers or not found."""
    held = {buffer.name: buffer.index for buffer in program.buffers}
    indices = {
        name: held.get(f"kField{generate.camel(name)}") for name in composition.streamed
    }
    past = {
        name: index
        for name, index in indices.items()
        if index is None or index >= STREAM_INDICES
    }
    if past:
        raise ValueError(
            f"frame program: stream halves at indices {past}, past the first "
            f"{STREAM_INDICES} a stream's half takes (every half: {indices})"
        )
    return indices
