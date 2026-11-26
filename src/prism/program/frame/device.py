"""The handler `work` on every core: a class made for one Composition, its hand kernels
the generated program (one file for both movers and the compute CPUs), its fields the
loop's rings, the outputs' pairs, the steps' and kinds' rings and the handler's memory.
"""

import komorebi as km

from prism.core import fields
from prism.core.compute import FRAME_COMPUTE
from prism.program.frame import generate
from prism_common.paths import build_root

ENTRY = "prism_frame::work"  # work_movement on both movers, work_compute on compute
HANDLER = "work"
WORD = 4


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

    class FrameWork(km.Program, compute=FRAME_COMPUTE):
        """WORK on every core of a view's pull: each core takes threads from its X280
        core, hands each to its compute CPUs and both movers, and runs it to its end."""

        __annotations__.update(annotations)  # the rings and the common fields
        vars().update(owns)
        vars().update(constants)

        @km.handler(km.kernel(movement=program_file, compute=program_file, entry=ENTRY))
        def work(self):
            """WORK: the threads of the command's pull (the block: the frame's
            page), each run where it was taken."""

    return FrameWork


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
