"""What the update leaves, read after the stop: its times rows, the work region's
arrays, the field's texels; and the reference's numbers to check them by."""

import numpy as np

from prism.stages.direct.light.model.field import field_pages
from prism.stages.indirect.field_update.model.numbers import (
    F32,
    PASS_APART,
    PASS_PARTS,
    TIMES_NAMES,
    TIMES_ROWS,
    TIMES_WORDS,
    U,
)
from prism.stages.indirect.field_update.model.regions import (
    counts,
    row_places,
    work_layout,
)
from prism_reference.indirect.field.pack import pack_field
from prism_reference.indirect.field.values import field_values
from prism_reference.indirect.light import element_light, field_source

TICKS_MS = 1e3 / 50e6  # a thread timer tick's milliseconds


def times(raw, ticks_ms=TICKS_MS):
    """The times region's rows (its bytes), oldest first: each update's parts in ms,
    each pass's (past PASS_APART passes the last entry their sum, `summed` the passes
    it holds), its number, code, step, passes, scale."""
    words = np.frombuffer(np.asarray(raw, np.uint8).tobytes(), dtype=np.uint32)
    rows = words[: TIMES_ROWS * TIMES_WORDS].reshape(-1, TIMES_WORDS)
    out = []
    for row in rows:
        if not row.any():
            continue
        entry = {
            name: round(row[U[key]] * ticks_ms, 4) for name, key in TIMES_NAMES.items()
        }
        passes = int(row[U["FU_T_PASSES"]])
        entry["passes_ms"] = [
            {
                part: round(
                    row[U["FU_T_PASS"] + U["FU_T_PASS_WORDS"] * p + k] * ticks_ms, 4
                )
                for k, part in enumerate(PASS_PARTS)
            }
            for p in range(min(passes, PASS_APART))
        ]
        if passes > PASS_APART:
            entry["summed"] = passes - PASS_APART + 1
        entry["number"] = int(row[U["FU_T_NUMBER"]])
        entry["code"] = int(row[U["FU_T_CODE"]])
        entry["step"] = int(row[U["FU_T_STEP"]])
        entry["passes"] = passes
        entry["scale"] = float(row[U["FU_T_SCALE"] : U["FU_T_SCALE"] + 1].view(F32)[0])
        at = U["FU_T_UNIT"]
        entry["unit"] = [float(v) for v in row[at : at + 3].view(F32)]
        out.append(entry)
    return sorted(out, key=lambda entry: entry["number"])


def work_arrays(raw, model):
    """sky, L0 and the total (e after the finish) [N, 3] float32 from the work region's
    bytes."""
    offsets, _ = work_layout(model)
    raw = np.asarray(raw, np.uint8)
    n = counts(model)["n"]

    def array(word):
        at = offsets[word]
        return raw[at : at + 12 * n].view(F32).reshape(n, 3).copy()

    return {"sky": array("w_sky"), "l0": array("w_l0"), "total": array("w_total")}


def field_texels(pages, model):
    """The field's texels (rows,) uint32 from its pages (field_pages' layout)."""
    places = row_places(model) & np.uint32(0x7FFFFFFF)
    return np.asarray(pages, np.uint32).ravel()[places]


def expected(lights, model, bounces):
    """The reference's numbers for `lights` (its shadow map: the card's when checking
    the card): sky, L0, the passes (E_p), the field's values (rows, 3), its texels
    (rows,), scale and pages."""
    lit = element_light(lights, model, bounces)
    values = field_values(model, field_source(lit))
    texels, scale = pack_field(values, model["field_has"])
    return {
        "sky": lit["sky"],
        "l0": lit["l0"],
        "passes": lit["passes"],
        "values": values.reshape(-1, 3),
        "texels": texels.ravel(),
        "scale": scale,
        "pages": field_pages(model, texels),
    }
