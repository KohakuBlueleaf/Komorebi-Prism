"""The direct-light stage on the card: one class, its handler LIGHT, each core's tiles'
surface planes into the frame's colour planes (hand kernels under kernels/)."""

import komorebi as km

from prism.core import fields
from prism.core.compute import FRAME_COMPUTE
from prism.stages.direct.light.model import numbers
from prism.stages.material.texture.model.table import stepped
from prism.stages.raster import capacity

LH, TP = numbers.LH, numbers.TEXEL_PAGES
PAGE = 4096  # a plane's page, a slot's, the out pages'
DIRECTORY_WORDS = PAGE // 4  # a directory page
TABLE_WORDS = LH["kLightTableBytes"] // 4  # LIGHT's table, SHADE's rows after it
PLANE_PAGES = 4 * LH["kLightPart"]  # the ring: an item's 15 or 20 pages, five a push
OUT_PAGES = 3 * LH["kLightOutPages"]  # three items' five pages
SLOT_PAGES = TP["kShadeSlots"] + 1  # the light pages' slots and the zero texels' page
ASK_WORDS = TP["kShadeAskBytes"] // 4
ASK_PAGES = TP["kShadeAskPages"]
DONE_WORDS = TP["kShadeDoneBytes"] // 4
DONE_PAGES = TP["kShadeDonePages"]
PAGES_WORK_WORDS = LH["kLightPagesBytes"] // 4  # the page passes' hash
PACK_WORK_WORDS = (
    LH["kLightPackBytes"] // 4
)  # texel indices (lit SHADE: slots), profile
ITEM_WORDS = LH["kLightItemWords"]
ITEM_SLOTS = LH["kLightItemSlots"]

LIGHT = km.kernel(
    reader="kernels/mover_a/light.hpp",
    writer="kernels/mover_b/light.hpp",
    unpack="kernels/unpack.hpp",
    pack="kernels/pack/light.hpp",
    entry="light_k::light",
)


fields.need("in_planes", "direct.light", lambda held: PLANE_PAGES)
fields.need(
    "frame_table",
    "direct.light",
    lambda held: stepped(TABLE_WORDS + (0 if held is None else held.table_rows)),
)
fields.need(
    "texel_slots",
    "direct.light",
    lambda held: SLOT_PAGES * numbers.SURFACE["kTexPageBytes"],
)
fields.need("texel_work", "direct.light", lambda held: 4 * PAGES_WORK_WORDS)
fields.need("pack_work", "direct.light", lambda held: 4 * PACK_WORK_WORDS)
fields.need("out_ring", "direct.light", lambda held: OUT_PAGES)


class Light(km.Program, compute=FRAME_COMPUTE):
    """LIGHT on every core of a group, as the X280 thread sends it; its grid's capacity
    that of the raster it follows (made)."""

    # the common fields' sizes (prism.core.fields), given at the make
    IN_PLANES_PAGES = fields.CONSTANTS["IN_PLANES_PAGES"]
    FRAME_TABLE_WORDS = fields.CONSTANTS["FRAME_TABLE_WORDS"]
    COMMAND_SPACE_WORDS = fields.CONSTANTS["COMMAND_SPACE_WORDS"]
    OUT_RING_PAGES = fields.CONSTANTS["OUT_RING_PAGES"]

    reader_page: km.L1[km.u32, 1, DIRECTORY_WORDS] = km.own(push=None, raw=True)
    writer_page: km.L1[km.u32, 1, DIRECTORY_WORDS] = km.own(push=None, raw=True)
    items: km.L1[km.u32, ITEM_SLOTS, ITEM_WORDS] = km.own(push="mover_a", raw=True)
    in_planes: fields.field("in_planes") = fields.own("in_planes")
    frame_table: fields.field("frame_table") = fields.own("frame_table")
    texel_asks: fields.field("texel_asks") = fields.own("texel_asks")
    texel_dones: fields.field("texel_dones") = fields.own("texel_dones")
    command_space: fields.field("command_space") = fields.own("command_space")
    out_ring: fields.field("out_ring") = fields.own("out_ring")

    @km.handler(LIGHT)
    def light(
        self,
        directory: km.Tensor,
        table: int,
        shade_table: int,
        camera: int,
        glass: km.Tensor,
        surface: km.Tensor,
        bank_grid: int,
        mode: int,
    ):
        """The frame's colour planes of the items of `directory` from `surface`'s planes
        under the table at `table` (bank of bank_grid; 0: the surface's), the camera
        at `camera`; `mode` displayed, linear, or glass over the linear (light.h)."""


SHOWN_PAGES = numbers.SHOW["kShowScratchPages"]  # mover B's pages, LIGHT shown
SHOWN_WORDS = numbers.SHOW["kShowPageBytes"] // 4


class LightShown(Light):
    """LIGHT with the option light_shows: mover B's scratch pages (two converted, the
    profile's, the buckets) for the display stage's conversion."""

    shown_scratch: km.L1[km.u32, SHOWN_PAGES, SHOWN_WORDS] = km.own(push=None, raw=True)


def shows_defines(host):
    """The kernels' define of the option light_shows (mover B converts for display)."""
    return {"PRISM_LIGHT_SHOWS": "1"} if host.shows else {}


def transmit_defines(host):
    """The kernels' define of the sun map's T (each lit shadow tap weighted by it)."""
    return {"PRISM_LIGHT_TRANSMIT": "1"} if host.transmit else {}


def made(host):
    """The class made for a host's tensors and the raster's capacity."""
    cls = LightShown if host.shows else Light
    return cls(
        **host.examples,
        **fields.given(cls, host.held),
        defines=capacity.capacity_defines(host.held)
        | fields.defines(host.held)
        | fields.table_defines(cls, host.held)
        | shows_defines(host)
        | transmit_defines(host),
        session=host.session,
        depth=1,
    )
