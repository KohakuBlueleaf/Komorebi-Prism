"""The sun map's T as the card keeps it (core/include/thread/transmit.h): whether a
pipeline has it (option shadow_transmit, and glass in the scene), its channels by the
scene's glass, its pages after the light pages' others, and the blocks as arrays."""

from pathlib import Path

import numpy as np

from prism.core.headers import INCLUDE, constexpr, defined
from prism_reference.direct.transmit import LOSS, t_channels
from prism_reference.material.kinds import TRANSPARENT

STAGES = Path(__file__).resolve().parents[3]
TH = defined(INCLUDE / "thread" / "transmit.h")
OPTION = "shadow_transmit"
DEFAULT = False
KERNEL = STAGES / "material" / "texture" / "kernels" / "transmit.hpp"
LOSS_BITS = constexpr(KERNEL)["kTransmitLossBits"]
PAGE = 32  # a map tile's side
WORD_BYTES = {1: 1, 3: 4}


def transmit_channels(options, materials):
    """T's channels for a pipeline of `options` on `materials`: 0 (none: not asked, or
    no glass), 1 (every glass material grey) or 3."""
    if materials is None or not options.get(OPTION, DEFAULT):
        return 0
    if not (materials["kind"][materials["material"]] == TRANSPARENT).any():
        return 0
    if int(np.float32(LOSS).view(np.uint32)) != LOSS_BITS:
        raise ValueError("direct.light: the card's glass loss is not the reference's")
    return t_channels(materials, np.arange(len(materials["material"])))


def block_bytes(channels):
    """A map tile's block: TRANSMIT_SIDE^2 texels of a byte (grey) or a word."""
    return TH["TRANSMIT_SIDE"] ** 2 * WORD_BYTES[channels]


def transmit_pages(side, channels):
    """The pages a map of `side` keeps its T in (0 without T)."""
    if not channels:
        return 0
    per = TH["TRANSMIT_PAGE_BYTES"] // block_bytes(channels)
    return -(-((side // PAGE) ** 2) // per)


def blocks_of(pages, side, channels):
    """The card's T of a map of `side` from its pages (pages, 1024) uint32: the codes
    (side / 2, side / 2, channels) uint8, its tiles' blocks put back in place."""
    per = TH["TRANSMIT_PAGE_BYTES"] // block_bytes(channels)
    tiles = (side // PAGE) ** 2
    raw = np.ascontiguousarray(pages).view(np.uint8).reshape(-1)
    k = TH["TRANSMIT_SIDE"]
    used = -(-tiles // per) * TH["TRANSMIT_PAGE_BYTES"]
    blocks = raw[:used].reshape(-1, block_bytes(channels))[:tiles]
    if channels == 1:
        texels = blocks.reshape(tiles, k, k, 1)
    else:
        texels = blocks.reshape(tiles, k, k, 4)[..., :3]
    across = side // PAGE
    out = texels.reshape(across, across, k, k, channels).transpose(0, 2, 1, 3, 4)
    return np.ascontiguousarray(out.reshape(across * k, across * k, channels))
