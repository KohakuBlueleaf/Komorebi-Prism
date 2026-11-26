"""SHADE's table: counts, the texel tables, the background, a row a material and a word
pair a (texture, level)."""

import numpy as np

from prism.stages.material.texture.model.numbers import F32, SH, SURFACE
from prism_reference.material.kinds import (
    ALBEDO,
    EMISSIVE,
    LIT,
    MASK,
    NORMAL,
    SPECULAR,
    TRANSPARENT,
)
from prism_reference.material.texture import TEXEL_LINEAR, TEXEL_SIGNED, TEXEL_UNIT
from prism_reference.raster.fill import BACKGROUND


def specular_term(materials):
    """Per material whether it has the Blinn-Phong term: lit or transparent with a
    specular colour."""
    shiny = (materials["kind"] == LIT) | (materials["kind"] == TRANSPARENT)
    return shiny & (materials["specular"].max(axis=1) > 0)


def exponents(materials):
    """Per material its specular exponent where it has a specular term, else 0: the
    material word's bits from kMaterialExponentShift."""
    has = specular_term(materials)
    exponent = np.where(has, materials["exponent"], 0).astype(np.int64)
    if (exponent < 0).any() or exponent.max(initial=0) > SURFACE["kExponentMax"]:
        raise ValueError(
            f"a specular exponent is outside 0 to {SURFACE['kExponentMax']}"
        )
    return exponent.astype(np.uint32)


def transmission(materials):
    """Per material its transmission tau (M, 3) float32: the materials file's where the
    kind is transparent, else 0 (a file without it: 0)."""
    tau = materials.get("transmission")
    if tau is None:
        return np.zeros((len(materials["kind"]), 3), dtype=F32)
    clear = materials["kind"] == TRANSPARENT
    return np.where(clear[:, None], tau, 0).astype(F32)


LEAST_WORDS = SH["kShadeTableLeastBytes"] // 4  # the table's least words
STEP_WORDS = SH["kShadeTableStepBytes"] // 4  # its words' step


def table_needs(materials):
    """The words SHADE's table needs for `materials`: (through the entries, through the
    last material row)."""
    rows = SH["kTabMaterial"] + SH["kMaterialWords"] * len(materials["kind"])
    entries = SH["kEntryWords"] * materials["mip"].shape[0] * materials["mip"].shape[1]
    return rows + entries, rows


def stepped(words):
    """`words` a table field holds: up to the step, at least LEAST_WORDS."""
    return max(LEAST_WORDS, -(-words // STEP_WORDS) * STEP_WORDS)


def table(materials, entries, pages, emissive_scale=1.0, size=None):
    """SHADE's table of `size` words (None: its stepped need): counts, the texel
    tables, the background, the materials (emissive bases x emissive_scale;
    transparent: tau and 1 - max tau), the (texture, level) entries."""
    count, levels = entries.shape[:2]
    size = stepped(table_needs(materials)[0]) if size is None else size
    words = np.zeros(size, dtype=np.uint32)
    materials_count = len(materials["kind"])
    words[SH["kTabMaterials"]] = materials_count
    words[SH["kTabEntries"]] = count * levels
    words[SH["kTabPages"]] = pages
    for name, values in (
        ("kTabGamma", TEXEL_LINEAR),
        ("kTabSigned", TEXEL_SIGNED),
        ("kTabUnit", TEXEL_UNIT),
    ):
        words[SH[name] : SH[name] + 256] = values.view(np.uint32)
    background = SH["kTabBackground"]
    words[background : background + 3] = BACKGROUND.view(np.uint32)
    at = SH["kTabMaterial"]
    albedo = materials["textures"][:, ALBEDO]
    rows = np.zeros((materials_count, SH["kMaterialWords"]), dtype=np.uint32)
    rows[:, 0] = (
        materials["kind"].astype(np.uint32)
        | np.where(albedo >= 0, albedo * levels + 1, 0).astype(np.uint32) << 8
    )
    rows[:, 1:4] = materials["base_colour"].astype(F32).view(np.uint32)
    mask = materials["textures"][:, MASK]
    for material in np.flatnonzero((mask >= 0) & (albedo >= 0)):
        texture, alpha = albedo[material], mask[material]
        same = (
            materials["levels"][texture] == materials["levels"][alpha]
            and (
                materials["mip"][texture, :, 1:] == materials["mip"][alpha, :, 1:]
            ).all()
        )
        if not same:
            raise ValueError(f"material {material}: mask and albedo sizes differ")
    rows[:, SH["kMaterialMask"]] = np.where(
        (mask >= 0) & (albedo >= 0), mask * levels + 1, 0
    ).astype(np.uint32)
    for name, slot in (("kMaterialNormal", NORMAL), ("kMaterialSpecular", SPECULAR)):
        own = materials["textures"][:, slot]
        rows[:, SH[name]] = np.where(own >= 0, own * levels + 1, 0).astype(np.uint32)
    emissive = materials["kind"] == EMISSIVE
    base = materials["base_colour"].astype(F32)
    lit_base = np.where(emissive[:, None], base * F32(emissive_scale), base)
    at_base = SH["kMaterialLitBase"]
    rows[:, at_base : at_base + 3] = lit_base.astype(F32).view(np.uint32)
    specular = materials["specular"].astype(F32)
    has = specular_term(materials)
    at_specular = SH["kMaterialSpecularColour"]
    rows[:, at_specular : at_specular + 3] = (
        np.where(has[:, None], specular, F32(0)).astype(F32).view(np.uint32)
    )
    rows[:, SH["kMaterialExponent"]] = exponents(materials)
    tau = transmission(materials)
    at_tau = SH["kMaterialTau"]
    rows[:, at_tau : at_tau + 3] = tau.view(np.uint32)
    rows[:, SH["kMaterialWeight"]] = (
        (F32(1) - tau.max(axis=1)).astype(F32).view(np.uint32)
    )
    end = at + rows.size
    entry_words = np.zeros((count * levels, SH["kEntryWords"]), dtype=np.uint32)
    entry_words[:, 0] = entries[:, :, 0].ravel()
    entry_words[:, 1] = entries[:, :, 1].ravel() | entries[:, :, 2].ravel() << 16
    if end + entry_words.size > len(words):
        raise ValueError(
            f"SHADE's table needs {end + entry_words.size} words and holds"
            f" {len(words)} (the field frame_table's words)"
        )
    words[at:end] = rows.ravel()
    words[end : end + entry_words.size] = entry_words.ravel()
    return words
