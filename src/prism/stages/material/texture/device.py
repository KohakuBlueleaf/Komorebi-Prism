"""The texture stage on the card: one class, its one handler SHADE (the unlit forms:
opaque, masked, glass; the lit forms: the surface's planes) as hand kernels on its own
fields."""

import komorebi as km

from prism.core import fields
from prism.core.compute import FRAME_COMPUTE
from prism.stages.direct.light.model.numbers import LH
from prism.stages.material.texture.model.numbers import PAGES, SH, SURFACE
from prism.stages.material.texture.model.table import stepped
from prism.stages.raster import capacity
from prism.stages.raster.model.numbers import K

WORD = 4  # bytes a word
PLANES = K["kPlanes"]  # an item's planes (pages)
LIST_PAGES = K["kInPages"]  # the core's list pages in flight
LIST_WORDS = K["kInPageBytes"] // WORD
OUT_PAGES = K["kOutPages"]  # items of kShadeOutPages: none wraps
PLANE_PAGES = SH["kShadePlanePages"]  # items of five, ten merging
WORK_WORDS = SH["kShadeWorkBytes"] // WORD
ASK_PAGES = PAGES["kShadeAskPages"]
ASK_WORDS = PAGES["kShadeAskBytes"] // WORD
DONE_PAGES = PAGES["kShadeDonePages"]
DONE_WORDS = PAGES["kShadeDoneBytes"] // WORD
SLOT_PAGES = PAGES["kShadeSlots"] + 1  # the slots and the white texel's page
PACK_WORK_WORDS = LH["kLightPackBytes"] // 4  # lit: the slots' words (LIGHT's field)
assert SURFACE["kTexPageBytes"] == 32 * 32 * WORD  # a slot is a tile's page

# SHADE's hand kernels: mover A reads, mover B writes, the unpack thread serves the
# pack thread's waits, the pack thread colours (lit: makes the surface's planes).
SHADE = km.kernel(
    reader="kernels/mover_a/reader.hpp",
    writer="kernels/mover_b/writer.hpp",
    unpack="kernels/unpack.hpp",
    pack="kernels/pack/pack.hpp",
    entry="shade_k::shade",
)


fields.need("in_planes", "material.texture", lambda held: PLANE_PAGES)
fields.need(
    "frame_table",
    "material.texture",
    lambda held: stepped(0 if held is None else held.table),
)
fields.need(
    "texel_slots",
    "material.texture",
    lambda held: SLOT_PAGES * SURFACE["kTexPageBytes"],
)
fields.need("texel_work", "material.texture", lambda held: WORD * WORK_WORDS)
fields.need("out_ring", "material.texture", lambda held: OUT_PAGES)
fields.need("pack_work", "material.texture", lambda held: WORD * PACK_WORK_WORDS)


class Shade(km.Program, compute=FRAME_COMPUTE):
    """SHADE on every core of a group: each core's directory items coloured from the
    textures' pages its pack thread asks for; merged or blended with an opaque layer."""

    # the common fields' sizes (prism.core.fields), given at the make
    IN_PLANES_PAGES = fields.CONSTANTS["IN_PLANES_PAGES"]
    FRAME_TABLE_WORDS = fields.CONSTANTS["FRAME_TABLE_WORDS"]
    COMMAND_SPACE_WORDS = fields.CONSTANTS["COMMAND_SPACE_WORDS"]
    OUT_RING_PAGES = fields.CONSTANTS["OUT_RING_PAGES"]

    shade_lists: km.L1[km.u32, LIST_PAGES, LIST_WORDS] = km.own(
        push="mover_a", raw=True
    )
    in_planes: fields.field("in_planes") = fields.own("in_planes")
    frame_table: fields.field("frame_table") = fields.own("frame_table")
    texel_asks: fields.field("texel_asks") = fields.own("texel_asks")
    texel_dones: fields.field("texel_dones") = fields.own("texel_dones")
    command_space: fields.field("command_space") = fields.own("command_space")
    out_ring: fields.field("out_ring") = fields.own("out_ring")
    # the pages a handler keeps to itself (common to the classes merged with it): the
    # surface's directory words, mover A's and mover B's (kernels: kDirA, kDirB)
    own_page_1: fields.field("own_page_1") = fields.own("own_page_1")
    own_page_2: fields.field("own_page_2") = fields.own("own_page_2")

    @km.handler(SHADE)
    def shade(
        self,
        directory: km.Tensor,
        lists: km.Tensor,
        textures: km.Tensor,
        table: km.Tensor,
        profile: km.Tensor,
        opaque: int,
        mode: int,
        grid: int,
        camera: int,
        surface: km.Tensor,
    ):
        """SHADE: the core's directory items' colour from its list's records and the
        textures; `opaque` the opaque layer's directory (0: not merging), `mode` the
        kShade* bits, `grid` the frame's; lit (`camera` the camera's address in the
        grid's bank, else 0): the surface's planes into `surface`'s frames."""


def transmit_defines(host):
    """The kernels' define of the sun map's T (SHADE's transmit mode)."""
    return {"PRISM_SHADE_TRANSMIT": "1"} if host.transmit else {}


def made(host):
    """The class made for a host's tensors and the capacity its frame is made for."""
    return Shade(
        **host.examples,
        **fields.given(Shade, host.held),
        defines=capacity.capacity_defines(host.held)
        | fields.defines(host.held)
        | fields.table_defines(Shade, host.held)
        | transmit_defines(host),
        session=host.session,
        depth=1,
    )
