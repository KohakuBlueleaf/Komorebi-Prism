"""LIGHT's terms as the table's bits, and its pages: the shadow map, the background's
three planes and the field, in pages of 32 x 32 values."""

import numpy as np

from prism.stages.direct.light.model.numbers import (
    BASE_TERMS,
    CARD_TERMS,
    F32,
    LH,
    PAGE,
)
from prism_reference.direct.frame import TERMS


def term_bits(terms):
    """The table's kLtTerms word of a set of the reference's terms (must hold
    BASE_TERMS; the sun's shadow only with the sun)."""
    terms = set(terms)
    unknown = terms - set(TERMS) - {"indirect"}
    if unknown or not set(BASE_TERMS) <= terms:
        raise ValueError(
            f"the card's terms: {BASE_TERMS} and any of {list(CARD_TERMS)}"
        )
    return sum(LH[name] for term, name in CARD_TERMS.items() if term in terms)


def map_pages(values):
    """A map (side, side) of 32-bit values in pages of 32 x 32, pages row by row, a
    page's values row by row from the top: (pages, 1024) uint32."""
    side = values.shape[0]
    blocks = values.reshape(side // PAGE, PAGE, side // PAGE, PAGE).transpose(
        0, 2, 1, 3
    )
    return np.ascontiguousarray(blocks.reshape(-1, PAGE * PAGE).view(np.uint32))


def light_pages(lights, field=None):
    """LIGHT's pages: the shadow map's 1/z, then the background map's red, green and
    blue planes, each a map_pages; with `field` (field_of) its pages after them (its
    `halves`, 1 when absent: the pages again, zero, for each half after the first);
    and each part's first page."""
    shadow = lights["shadow_map"].astype(F32)
    octa = lights["octahedral"].astype(F32)
    if shadow.shape[0] % PAGE or octa.shape[0] % PAGE:
        raise ValueError("a light map's side is not a multiple of 32")
    parts = [map_pages(shadow)] + [map_pages(octa[:, :, c]) for c in range(3)]
    first = {"shadow": 0, "octahedral": len(parts[0])}
    if field is not None:
        first["field"] = sum(len(part) for part in parts)
        parts.append(field["pages"])
        parts += [np.zeros_like(field["pages"])] * (field.get("halves", 1) - 1)
    return np.concatenate(parts), first


def light_pages_first(lights):
    """The field's first page in light_pages: after the shadow and background maps."""
    shadow, octa = lights["shadow_map"].shape[0], lights["octahedral"].shape[0]
    return (shadow // PAGE) ** 2 + 3 * (octa // PAGE) ** 2
