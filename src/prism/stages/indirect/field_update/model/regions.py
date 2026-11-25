"""The field update's regions as the host fills them: the operator by row, each row's
place in the field's pages, the elements' arrays and region, the counts, the work
region's layout."""

import numpy as np

from prism.stages.direct.light.model.field import (
    FIELD_BLOCK,
    FIELD_DIRECTION,
    field_layout,
)
from prism.stages.indirect.field_update.model.numbers import (
    ALIGN,
    ELEMENT_ARRAYS,
    F32,
    PAGE_TEXELS,
    TILE,
    WORK_ARRAYS,
    X_PAGE,
    Y_PAGE,
)
from prism_reference.indirect.light import lamp_irradiance


def aligned(at):
    """`at` rounded up to whole ALIGN."""
    return -(-at // ALIGN) * ALIGN


def operator_rows(model):
    """The field's operator by row (field_values' sparse sum): each row's first pair
    (rows + 1 starts) and the (column, weight) pairs in the reference's order (uint32
    [weights, 2], the weight's float32 bits)."""
    rows = model["field_rows"]
    count = len(model["field_keys"]) * 6
    if len(rows) and np.any(np.diff(rows) < 0):
        raise ValueError("the field's rows are not in order")
    starts = np.searchsorted(rows, np.arange(count + 1)).astype(np.uint32)
    pairs = np.empty((len(rows), 2), dtype=np.uint32)
    pairs[:, 0] = model["field_columns"].astype(np.uint32)
    pairs[:, 1] = model["field_weights"].astype(F32).view(np.uint32)
    return starts, pairs


def row_places(model):
    """Each row's (voxel x 6 + d) place in the field's pages (field_pages' layout):
    page x 1,024 + texel, bit 31 where the row has data (uint32 [rows])."""
    blocks, _ = field_layout(model)
    dims = tuple(int(d) for d in model["field_dims"])
    voxel = np.stack(np.unravel_index(model["field_keys"], dims), -1)
    block, inside = voxel // FIELD_BLOCK, voxel % FIELD_BLOCK
    page = (block[:, 1] * blocks[2] + block[:, 2]) * blocks[0] + block[:, 0]
    local = (inside[:, 1] * FIELD_BLOCK[2] + inside[:, 2]) * FIELD_BLOCK[0] + inside[
        :, 0
    ]
    texel = np.arange(6) * FIELD_DIRECTION + local[:, None]
    places = (page[:, None] * PAGE_TEXELS + texel).astype(np.uint64)
    if places.size and places.max() >= 1 << 31:
        raise ValueError("the field's pages pass 2^31 texels")
    has = model["field_has"].astype(np.uint64) << 31
    return (places | has).astype(np.uint32).ravel()


def element_arrays(model, lights):
    """The elements' arrays the thread reads (float32 [N, 3] or [N, 25]): position,
    normal, base = emission x emissive_scale + albedo / pi x the lamps, albedo / pi,
    transfer; base and albedo / pi 0 on pad rows."""
    p, n = model["position"].astype(F32), model["normal"].astype(F32)
    real = model["real"][:, None]
    albedo_pi = model["albedo"] * F32(1 / np.pi)
    base = model["emission"] * F32(lights["emissive_scale"]) + albedo_pi * (
        lamp_irradiance(lights, p, n)
    )
    return {
        "position": p,
        "normal": n,
        "base": np.where(real, base, F32(0)).astype(F32),
        "albedo": np.where(real, albedo_pi, F32(0)).astype(F32),
        "transfer": model["transfer"].astype(F32),
    }


def laid(parts):
    """{name: byte offset} of (name, bytes) parts, each from a whole ALIGN, and the end."""
    offsets, at = {}, 0
    for name, size in parts:
        offsets[name] = at
        at = aligned(at + size)
    return offsets, at


def elements_region(model, lights):
    """The elements region (uint8) and its arrays' byte offsets {header word: offset}."""
    arrays = element_arrays(model, lights)
    starts, pairs = operator_rows(model)
    values = [
        arrays["position"],
        arrays["normal"],
        arrays["base"],
        arrays["albedo"],
        arrays["transfer"],
        starts,
        pairs,
        row_places(model),
    ]
    parts = list(zip(ELEMENT_ARRAYS, values, strict=True))
    offsets, end = laid([(name, array.nbytes) for name, array in parts])
    region = np.zeros(end, dtype=np.uint8)
    for name, array in parts:
        raw = np.ascontiguousarray(array).view(np.uint8).ravel()
        region[offsets[name] : offsets[name] + raw.size] = raw
    return region, offsets


def counts(model):
    """N, x tiles, rows, weights, field pages of a model."""
    n = len(model["position"])
    if n % TILE:
        raise ValueError(f"{n} elements: not a multiple of {TILE}")
    _, pages = field_layout(model)
    return {
        "n": n,
        "tiles": n // TILE,
        "rows": len(model["field_keys"]) * 6,
        "weights": len(model["field_rows"]),
        "pages": pages,
    }


def work_layout(model):
    """The work region's arrays' byte offsets {header word: offset} and its bytes."""
    c = counts(model)
    sizes = (
        12 * c["n"],
        12 * c["n"],
        12 * c["n"],
        X_PAGE * c["tiles"],
        Y_PAGE * c["tiles"],
        12 * c["rows"],
    )
    return laid(list(zip(WORK_ARRAYS, sizes, strict=True)))
