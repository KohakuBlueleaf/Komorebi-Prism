"""glTF accessors as numpy arrays: every component type and type, byteStride, normalized
integers to float32, sparse substitution; views over the buffer where the type allows.
"""

import numpy as np

from prism_reference.scene.importers.gltf.container import view_bytes

COMPONENTS = {
    5120: np.dtype("i1"),
    5121: np.dtype("u1"),
    5122: np.dtype("<i2"),
    5123: np.dtype("<u2"),
    5125: np.dtype("<u4"),
    5126: np.dtype("<f4"),
}
# type: (columns, rows); a vector or scalar is one column
TYPES = {
    "SCALAR": (1, 1),
    "VEC2": (1, 2),
    "VEC3": (1, 3),
    "VEC4": (1, 4),
    "MAT2": (2, 2),
    "MAT3": (3, 3),
    "MAT4": (4, 4),
}


def _shape(kind, count):
    """The array shape of `count` elements of `kind`."""
    columns, rows = TYPES[kind]
    if kind == "SCALAR":
        return (count,)
    return (count, rows) if columns == 1 else (count, rows, columns)


def _elements(container, view, offset, dtype, kind, count, what):
    """`count` elements of `kind` in buffer view `view` from `offset`, without a copy."""
    columns, rows = TYPES[kind]
    size = dtype.itemsize
    column_stride = rows * size if columns == 1 else (rows * size + 3) & ~3
    element = columns * column_stride
    data, stride = view_bytes(container, view)
    stride = stride or element
    if count and offset + stride * (count - 1) + element > len(data):
        raise ValueError(f"{what}: past the end of its buffer view")
    array = np.ndarray(
        (count, columns, rows),
        dtype,
        buffer=data,
        offset=offset,
        strides=(stride, column_stride, size),
    )
    if kind == "SCALAR":
        return array[:, 0, 0]
    return array[:, 0, :] if columns == 1 else array.transpose(0, 2, 1)


def _sparse(container, entry, base, dtype, index):
    """A new array: `base` with the elements `sparse.indices` names replaced by values."""
    sparse = entry["sparse"]
    out = np.array(base, copy=True)
    count = sparse["count"]
    where = sparse["indices"]
    index_type = COMPONENTS.get(where["componentType"])
    if where["componentType"] not in (5121, 5123, 5125):
        raise ValueError(
            f"accessor {index}: sparse index type {where['componentType']}"
        )
    what = f"accessor {index} sparse"
    rows = _elements(
        container,
        where["bufferView"],
        where.get("byteOffset", 0),
        index_type,
        "SCALAR",
        count,
        what,
    )
    if count and int(rows.max()) >= len(out):
        raise ValueError(f"{what}: index {int(rows.max())} at or past {len(out)}")
    values = sparse["values"]
    out[rows] = _elements(
        container,
        values["bufferView"],
        values.get("byteOffset", 0),
        dtype,
        entry["type"],
        count,
        what,
    )
    return out


def stored(container, index):
    """Accessor `index` in its stored component type; matrices (count, rows, columns)."""
    entry = container.doc["accessors"][index]
    dtype = COMPONENTS.get(entry["componentType"])
    if dtype is None:
        raise ValueError(f"accessor {index}: component type {entry['componentType']}")
    kind, count = entry["type"], entry["count"]
    if kind not in TYPES:
        raise ValueError(f"accessor {index}: type {kind}")
    if "bufferView" in entry:
        base = _elements(
            container,
            entry["bufferView"],
            entry.get("byteOffset", 0),
            dtype,
            kind,
            count,
            f"accessor {index}",
        )
    else:
        base = np.zeros(_shape(kind, count), dtype)
    if "sparse" in entry:
        return _sparse(container, entry, base, dtype, index)
    return base


def normalized(array):
    """Integers converted to float32 by glTF's rule for normalized components."""
    info = np.iinfo(array.dtype)
    if info.min < 0:
        return np.maximum(array / np.float64(info.max), -1.0).astype(np.float32)
    return (array / np.float64(info.max)).astype(np.float32)


def read(container, index):
    """Accessor `index` as an array: normalized integers as float32, else stored."""
    array = stored(container, index)
    if container.doc["accessors"][index].get("normalized") and array.dtype.kind in "iu":
        return normalized(array)
    return array


def floats(container, index):
    """Accessor `index` as float32 (a view when stored as float32)."""
    return read(container, index).astype(np.float32, copy=False)


def triangle_indices(container, index):
    """An index accessor as (T, 3) uint32 (a view when stored as uint32)."""
    flat = stored(container, index).astype(np.uint32, copy=False)
    if len(flat) % 3:
        raise ValueError(f"accessor {index}: {len(flat)} indices, not a multiple of 3")
    return flat.reshape(-1, 3)
