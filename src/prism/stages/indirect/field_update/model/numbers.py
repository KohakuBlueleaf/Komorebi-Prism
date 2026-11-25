"""The field update's numbers: its C header's (thread/indirect_field_update.h), the
header region's words by name and their places, the director's numbers it asks for."""

from pathlib import Path

import numpy as np

from prism.core.headers import defined

F32 = np.float32
STAGE = Path(__file__).resolve().parent.parent
THREAD = STAGE / "thread"
U = defined(THREAD / "indirect_field_update.h")

SKY_TERMS = U["FU_SKY_TERMS"]
PAGE_TEXELS = U["FU_PAGE_TEXELS"]
PAGE_BYTES = U["FU_PAGE_BYTES"]
X_PAGE = U["FU_X_PAGE_BYTES"]
Y_PAGE = U["FU_Y_PAGE_BYTES"]
ALIGN = U["FU_ALIGN"]
TILE = U["FU_TILE"]
TIMES_ROWS = U["FU_TIMES_ROWS"]
TIMES_WORDS = U["FU_T_WORDS"]
PASS_APART = U["FU_T_PASS_APART"]  # the passes the times row tells apart
STEPS = {
    "all": U["FU_STEP_ALL"],
    "sources": U["FU_STEP_SOURCES"],
    "pass": U["FU_STEP_PASS"],
    "finish": U["FU_STEP_FINISH"],
}

# the header region's words in order: (name, words); the elements' and the work's
# arrays as byte offsets, then the sun's words the host writes on each change
ELEMENT_ARRAYS = (
    "e_position",
    "e_normal",
    "e_base",
    "e_albedo",
    "e_transfer",
    "e_starts",
    "e_pairs",
    "e_places",
)
WORK_ARRAYS = ("w_sky", "w_l0", "w_total", "w_x", "w_y", "w_values")
SUN_WORDS = (
    ("bounces", 1),
    ("texel", 1),
    ("bias", 1),
    ("sun", 3),
    ("irradiance", 3),
    ("camera", 16),
    ("sky", 3 * SKY_TERMS),
)
HEADER = (
    ("n", 1),
    ("tiles", 1),
    ("rows", 1),
    ("weights", 1),
    ("pages", 1),
    ("shadow_pages", 1),
    ("side", 1),
    ("x_page", 1),
    ("y_page", 1),
    *((name, 1) for name in ELEMENT_ARRAYS),
    *((name, 1) for name in WORK_ARRAYS),
    *SUN_WORDS,
)


def places(words):
    """{name: first word} of (name, words) pairs laid one after another, and the end."""
    out, at = {}, 0
    for name, count in words:
        out[name] = at
        at += count
    return out, at


H, HEADER_WORDS = places(HEADER)
HEADER_BYTES = -(-4 * HEADER_WORDS // 64) * 64
SUN_FIRST = H[SUN_WORDS[0][0]]
TIMES_BYTES = 4 * TIMES_ROWS * TIMES_WORDS
# the director's numbers it asks for: the tensors it fetches from and stores into
# (address, first page), x and y of the passes, the cores that copy
NUMBERS = (
    "update_cores",
    "update_shadow",
    "update_shadow_first",
    "update_field",
    "update_field_first",
    "update_x",
    "update_y",
)
# the times row's words by name, and a pass's parts
TIMES_NAMES = {
    "fetch": "FU_T_FETCH",
    "sources": "FU_T_SOURCES",
    "rows": "FU_T_ROWS",
    "pack": "FU_T_PACK",
    "store": "FU_T_STORE",
    "table": "FU_T_TABLE",
    "zero": "FU_T_ZERO",
    "total": "FU_T_TOTAL",
}
PASS_PARTS = ("store", "apply", "fetch", "next")


def header_defines():
    """The C's FU_H_<NAME> word places and FU_HEADER_WORDS: {name: text}."""
    out = {f"FU_H_{name.upper()}": f"{at}u" for name, at in H.items()}
    out["FU_HEADER_WORDS"] = f"{HEADER_WORDS}u"
    return out
