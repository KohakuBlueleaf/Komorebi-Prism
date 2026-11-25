"""The apply on the card: one handler, the hand-written kernels in kernels/."""

import inspect
from functools import cache

import komorebi as km

from prism.core import fields

APPLY = km.kernel(
    reader="kernels/apply_reader.hpp",
    writer="kernels/apply_writer.hpp",
    compute="kernels/apply_compute.hpp",
    entry="apply_k::apply",
)
BLOCKS_A_HALF = 4  # weight blocks in each half of w's pair
TOKEN_PAGES = 2  # the token's pages
Y_PAGES = 2  # y's pages in flight
# the buffers a frame program's Apply declares one page each and places, for its
# command, inside the common field command_space (kernels/apply_window.hpp)
WINDOWS = ("x_in", "w_in", "sums", "t", "token", "y_page")


class Apply(km.Program, compute={"math_fidelity": "HiFi2"}):
    """apply: y = M x. Core c's entries are its table pages; its own receiver tiles
    are summed in L1 and written to y."""

    OWN = km.constant(16)  # own receiver tiles, most
    KMAX = km.constant(77)  # x's tiles of an entry, most
    RANK = km.constant(5)  # rank tiles, most
    PAGES = km.constant(1)  # table pages a core
    BLOCK = km.constant(8)  # weight tiles a block
    x_in = km.Pair(km.bf16, pages=KMAX)
    w_in = km.Pair(km.bfp8_b, pages=BLOCK * BLOCKS_A_HALF)
    sums: km.L1[km.fp32, OWN, 32, 32] = km.own(push=None)
    t: km.L1[km.bf16, RANK, 32, 32] = km.own(push=None)  # t = x V, as t^T
    token: km.L1[km.bf16, TOKEN_PAGES, 32, 32] = km.own(push="pack")
    y_page: km.L1[km.fp32, Y_PAGES, 32, 32] = km.own(push="pack")
    apply_profile: km.L1[km.u32, 1, 32, 32] = km.own(push="pack")
    table: km.L1[km.u32, 1, 32, 32] = km.own(push="mover_a")
    head: km.L1[km.u32, 1, 32, 32] = km.own(push="mover_a")
    # the pages a handler keeps to itself (common to the classes merged with it):
    # mover B's table page and head page (kernels: kTableB, kHeadB)
    own_page_1: fields.field("own_page_1") = fields.own("own_page_1")
    own_page_2: fields.field("own_page_2") = fields.own("own_page_2")

    @km.handler(APPLY)
    def apply(
        self,
        x: km.Tensor,
        w: km.Tensor,
        y: km.Tensor,
        tables: km.Tensor,
        profile: km.Tensor,
    ):
        """y = M x on every core of the group."""


@cache
def joined(compute):
    """Apply as it joins a frame program of the compute set `compute` (sorted
    (option, value) pairs): its float32 fields unpacked to Dst as its own are, the
    common field command_space declared, WINDOWS one page each."""
    declared = inspect.get_annotations(Apply)
    pairs = {name: getattr(Apply, name) for name in WINDOWS if name not in declared}
    attributes = {
        "__module__": Apply.__module__,
        "__doc__": Apply.__doc__,
        "__annotations__": {
            "command_space": fields.field("command_space"),
            **{
                name: km.L1[declared[name].format, 1, 32, 32]
                for name in WINDOWS
                if name in declared
            },
        },
        "command_space": fields.own("command_space"),
        "COMMAND_SPACE_WORDS": fields.CONSTANTS["COMMAND_SPACE_WORDS"],
        **{name: km.Pair(pair.format, pages=1) for name, pair in pairs.items()},
    }
    return type("Apply", (Apply,), attributes, compute=dict(compute))


def window_defines(sizes, block):
    """The kernels' defines of the windows: each buffer of WINDOWS, its pages as the
    class alone declares them and its page's bytes."""
    pages = {
        "x_in": sizes["k_most"],
        "w_in": block * BLOCKS_A_HALF,
        "sums": sizes["own_most"],
        "t": sizes["rank_most"],
        "token": TOKEN_PAGES,
        "y_page": Y_PAGES,
    }
    annotated = inspect.get_annotations(Apply)
    out = {"APPLY_WINDOWS": "1"}
    for name in WINDOWS:
        declared = getattr(Apply, name)
        kind = declared if isinstance(declared, km.Pair) else annotated[name]
        out[f"APPLY_PAGES_{name.upper()}"] = str(pages[name])
        out[f"APPLY_BYTES_{name.upper()}"] = str(kind.format.tile_bytes)
    return out


def windows_bytes(defines):
    """The windows' bytes end to end as kernels/apply_window.hpp lays them (x's and
    w's halves two windows each, each from a 64-byte line), from window_defines."""
    at = 0
    for name in ("x_in", "x_in", "w_in", "w_in", *WINDOWS[2:]):
        at = -(-at // 64) * 64
        tag = name.upper()
        at += int(defines[f"APPLY_PAGES_{tag}"]) * int(defines[f"APPLY_BYTES_{tag}"])
    return at


def made(host):
    """Apply made for a host's set (its tensors and sizes): alone (the host's
    `compute` None) as it is, else in its frame program's form (joined)."""
    sizes = host.sizes
    framed = host.compute is not None
    program = joined(tuple(sorted(host.compute.items()))) if framed else Apply
    windows = window_defines(sizes, host.block)
    if framed and windows_bytes(windows) > fields.space_bytes(host.held):
        raise ValueError(
            f"the apply's windows take {windows_bytes(windows)} B, over the command "
            f"space's {fields.space_bytes(host.held)} B"
        )
    return program(
        **host.tensors,
        **fields.given(program, host.held),
        OWN=sizes["own_most"],
        KMAX=sizes["k_most"],
        RANK=sizes["rank_most"],
        PAGES=sizes["table_pages"],
        BLOCK=host.block,
        session=host.session,
        **({"defines": windows} if framed else {}),
    )
